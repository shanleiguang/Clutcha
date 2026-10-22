"""Observable state: the live log, counters and the metrics history.

Everything the Status tab draws comes from here: an in-memory log, counters
for the cards, and an append-only `metrics.jsonl` so the charts survive a
restart.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from datetime import datetime

from . import __version__
from . import config as cfg

METRICS_PATH = os.path.join(cfg.STATE_DIR, "metrics.jsonl")
METRICS_KEEP_SECONDS = 7 * 24 * 3600
METRICS_MAX_BYTES = 4 * 1024 * 1024

EVENT_KINDS = ("receive", "send", "error", "poll", "agent", "service", "runtime")


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.log: deque[dict] = deque(maxlen=800)
        self.events: deque[tuple[float, str, float | None]] = deque(maxlen=40000)
        self.started_at = time.time()
        self.polls = 0
        self.received = 0
        self.replied = 0
        self.errors = 0
        self.last_poll_at: float | None = None
        self.last_poll_result = "—"
        self.next_poll_at: float | None = None
        self.polling = False
        self.last_reply_ms: float | None = None
        self.last_reply_at: float | None = None
        self.wake = threading.Event()
        self._load_history()

    # -- log ---------------------------------------------------------------- #

    def add(self, kind: str, message: str, level: str = "info", duration_ms: float | None = None) -> None:
        now = time.time()
        entry = {"ts": now, "level": level, "kind": kind, "message": message}
        if duration_ms is not None:
            entry["ms"] = round(duration_ms, 1)
        with self.lock:
            self.log.appendleft(entry)
            self.events.append((now, kind, duration_ms))
        self._persist(now, kind, duration_ms)
        stamp = datetime.fromtimestamp(now).strftime("%H:%M:%S")
        print(f"[{stamp}] {kind.upper():8} {message}", flush=True)

    def bump(self, field: str, amount: int = 1) -> None:
        with self.lock:
            setattr(self, field, getattr(self, field) + amount)

    # -- metrics file ------------------------------------------------------- #

    def _persist(self, ts: float, kind: str, duration_ms: float | None) -> None:
        try:
            if os.path.exists(METRICS_PATH) and os.path.getsize(METRICS_PATH) > METRICS_MAX_BYTES:
                self._rotate()
            line = json.dumps({"t": round(ts, 1), "e": kind, "ms": duration_ms}, separators=(",", ":"))
            with open(METRICS_PATH, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass

    def _rotate(self) -> None:
        try:
            os.replace(METRICS_PATH, METRICS_PATH + ".1")
        except Exception:
            pass

    def _load_history(self) -> None:
        cutoff = time.time() - METRICS_KEEP_SECONDS
        try:
            with open(METRICS_PATH, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    ts = float(item.get("t") or 0)
                    if ts < cutoff:
                        continue
                    self.events.append((ts, item.get("e") or "?", item.get("ms")))
        except Exception:
            pass

    # -- derived ------------------------------------------------------------ #

    def buckets(self, hours: int = 24) -> list[dict]:
        """One bucket per hour: messages in/out, poll outcomes, average latency."""
        now = time.time()
        start = now - hours * 3600
        rows = [{"in": 0, "out": 0, "ok": 0, "empty": 0, "error": 0, "ms": 0.0, "n": 0} for _ in range(hours)]
        with self.lock:
            events = list(self.events)
        for ts, kind, duration_ms in events:
            if ts < start:
                continue
            index = int((ts - start) // 3600)
            if not 0 <= index < hours:
                continue
            row = rows[index]
            if kind == "receive":
                row["in"] += 1
            elif kind == "send":
                row["out"] += 1
            elif kind == "error":
                row["error"] += 1
            elif kind == "poll":
                row["empty"] += 1
            elif kind == "agent":
                row["ok"] += 1
                if duration_ms:
                    row["ms"] += duration_ms
                    row["n"] += 1
        for row in rows:
            row["latency"] = round(row["ms"] / row["n"], 1) if row["n"] else None
        return rows

    def snapshot(self) -> dict:
        with self.lock:
            log = [
                {**entry, "time": datetime.fromtimestamp(entry["ts"]).strftime("%Y-%m-%d %H:%M:%S")}
                for entry in list(self.log)[:80]
            ]
        session = cfg.session()
        letter = cfg.mail_template()
        return {
            "version": __version__,
            "startedAt": self.started_at,
            "uptime": round(time.time() - self.started_at),
            "polls": self.polls,
            "received": self.received,
            "replied": self.replied,
            "errors": self.errors,
            "lastPollAt": self.last_poll_at,
            "lastPollResult": self.last_poll_result,
            "nextPollAt": self.next_poll_at,
            "polling": self.polling,
            "lastReplyMs": self.last_reply_ms,
            "lastReplyAt": self.last_reply_at,
            "pollInterval": cfg.poll_cfg().get("intervalSeconds"),
            "configured": cfg.is_configured(),
            "mail": {
                "address": cfg.address(),
                "lang": letter.get("lang") or "auto",
            },
            "agent": {
                "name": cfg.monkey().get("name"),
                "harness": session.get("harness"),
                "tools": session.get("tools"),
                "sessionId": session.get("sessionId"),
                "cwd": session.get("cwd"),
                "timeoutSeconds": session.get("timeoutSeconds"),
            },
            "log": log,
        }


STATE = State()
