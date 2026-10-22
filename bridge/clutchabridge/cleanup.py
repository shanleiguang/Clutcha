"""Delete yesterday's letters, once a day, at the hour the user picked.

The mailbox is shared with the phone: every exchange leaves two letters behind
(the app's, the bridge's), permanently, and a mailbox that only ever grows is
eventually a problem for the provider as much as for the user. So there is a
janitor, off by default, with one rule that keeps it from being dangerous:

**It only deletes letters this bridge wrote, or letters the app addressed to it,
and only those dated yesterday, and only those already read.**

Anything else in the mailbox — a real email, a letter from today, a message the
cursor has never seen — is left alone. A cleanup that guesses is worse than a
mailbox that fills up.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import imaplib
import json
import os
import poplib
from email import message_from_bytes

from . import config as cfg
from . import mail
from .state import STATE

STATE_PATH = os.path.join(cfg.STATE_DIR, ".cleanup.json")
LOG_PATH = os.path.join(cfg.STATE_DIR, ".cleanup_log.jsonl")
LOG_KEEP = 300

# A run that fails is retried, but not every poll: three attempts a day, half an
# hour apart. Without this a mailbox that answers `-ERR System error` at 03:00
# would be knocked on every cycle until midnight.
MAX_ATTEMPTS = 3
COOLDOWN = 30 * 60

# One of these, once a day, right after the hour passes.
HOURS = (1, 3, 5, 7)

# Markers of our own traffic. The app writes X-VMessager; the bridge writes
# X-Clutcha and X-VMessager-Reply. Armor in the body is the last resort, for a
# letter whose headers were rewritten in transit.
OUR_HEADERS = ("X-Clutcha", "X-VMessager", "X-VMessager-Reply")
ARMOR_MARK = "-----BEGIN VM MESSAGE-----"

# A letter is a few kilobytes. Anything much larger is unlikely to be one of
# ours, and reading it costs the mailbox a round trip.
MAX_BYTES = 200 * 1024


def load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except Exception:
        pass


def log_line(entry: dict) -> None:
    """One line per run, appended. The activity log forgets; this does not."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        _trim_log()
    except Exception:
        pass


def _trim_log() -> None:
    try:
        if os.path.getsize(LOG_PATH) < 64 * 1024:
            return
        with open(LOG_PATH, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        with open(LOG_PATH, "w", encoding="utf-8") as handle:
            handle.writelines(lines[-LOG_KEEP:])
    except Exception:
        pass


def load_log(limit: int = 60) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return list(reversed(rows[-limit:]))


def _is_ours(message) -> bool:
    if any(message.get(header) for header in OUR_HEADERS):
        return True
    try:
        body = message.get_payload(decode=True) or b""
    except Exception:
        return False
    return ARMOR_MARK.encode() in body


def _day_of(message) -> dt.date | None:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone().date()
    except Exception:
        return None


def clean_pop3(target: dt.date) -> dict:
    inbox = cfg.mailbox()["inbox"]
    client = mail.step("connect", lambda: poplib.POP3_SSL(inbox["host"], int(inbox["port"]), timeout=mail.TIMEOUT))
    examined = 0
    deleted = 0
    try:
        mail.step("login", lambda: (client.user(inbox["username"]), client.pass_(inbox["token"])))
        _, lines, _ = mail.step("uidl", client.uidl)
        seen = mail.load_cursor()
        candidates = []
        for line in lines:
            parts = line.decode().split()
            if len(parts) != 2:
                continue
            number, uid = int(parts[0]), parts[1]
            # Unread means unseen: the cursor is the record of what has been read.
            if uid not in seen:
                continue
            candidates.append((number, uid))

        for number, uid in candidates:
            try:
                _, sizes, _ = client.list(number)
                size = int(sizes[0].decode().split()[1])
                if size > MAX_BYTES:
                    continue
                _, raw, _ = client.retr(number)
            except Exception:
                continue
            message = message_from_bytes(b"\r\n".join(raw))
            examined += 1
            if _day_of(message) != target or not _is_ours(message):
                continue
            try:
                client.dele(number)
                deleted += 1
            except Exception as error:
                STATE.add("cleanup", f"could not delete {uid}: {mail.error_text(error)}", "warn")
        # QUIT commits the deletions; a session that never quits marks them and
        # throws the marks away.
        client.quit()
        return {"ok": True, "examined": examined, "deleted": deleted}
    finally:
        try:
            client.quit()
        except Exception:
            pass


def clean_imap(target: dt.date) -> dict:
    inbox = cfg.mailbox()["inbox"]
    client = imaplib.IMAP4_SSL(inbox["host"], int(inbox["port"]), timeout=mail.TIMEOUT)
    examined = 0
    deleted = 0
    try:
        client.login(inbox["username"], inbox["token"])
        client.select("INBOX")
        stamp = target.strftime("%d-%b-%Y")
        status, data = client.search(None, f'(SINCE "{stamp}")')
        if status != "OK":
            return {"ok": False, "error": "search failed"}
        for uid in data[0].split():
            status, payload = client.fetch(uid, "(RFC822.SIZE BODY.PEEK[HEADER])")
            if status != "OK":
                continue
            raw = payload[0][1] if isinstance(payload[0], tuple) else b""
            message = message_from_bytes(raw)
            examined += 1
            if _day_of(message) != target or not _is_ours(message):
                continue
            client.store(uid, "+FLAGS", "\\Deleted")
            deleted += 1
        client.expunge()
        return {"ok": True, "examined": examined, "deleted": deleted}
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _record_attempt(ok: bool, deleted: int, examined: int) -> None:
    state = load_state()
    today = dt.date.today().isoformat()
    same_day = state.get("attemptDate") == today
    state["attemptDate"] = today
    state["attempts"] = (int(state.get("attempts") or 0) + 1) if same_day else 1
    state["lastAttempt"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    state["lastOk"] = ok
    if ok:
        state["lastRun"] = today
        state["deleted"] = deleted
        state["attempts"] = 0
    save_state(state)


def run(force: bool = False) -> dict:
    """Delete yesterday's letters now. Called by the loop, and by the page."""
    block = cfg.cleanup_cfg()
    if not force and not block.get("enabled"):
        return {"ok": False, "error": "cleanup is off"}
    target = dt.date.today() - dt.timedelta(days=1)
    protocol = (cfg.mailbox()["inbox"].get("protocol") or "pop3").lower()
    try:
        result = clean_imap(target) if protocol == "imap" else clean_pop3(target)
    except Exception as error:
        STATE.add("cleanup", f"cleanup failed: {error}", "error")
        _record_attempt(False, 0, 0)
        log_line({
            "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "target": target.isoformat(),
            "deleted": 0,
            "examined": 0,
            "ok": False,
            "error": str(error),
        })
        return {"ok": False, "error": str(error)}
    entry = {
        "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "target": target.isoformat(),
        "deleted": result.get("deleted", 0),
        "examined": result.get("examined", 0),
        "ok": bool(result.get("ok")),
    }
    if not entry["ok"]:
        entry["error"] = result.get("error") or "failed"
    log_line(entry)
    _record_attempt(entry["ok"], entry["deleted"], entry["examined"])
    if result.get("ok"):
        STATE.add(
            "cleanup",
            f"deleted {entry['deleted']} letter(s) from {target.isoformat()} "
            f"({entry['examined']} examined)",
        )
    return result


def due(now: dt.datetime | None = None) -> bool:
    block = cfg.cleanup_cfg()
    if not block.get("enabled"):
        return False
    moment = now or dt.datetime.now()
    hour = int(block.get("hour") or HOURS[1])
    if moment.hour < hour:
        return False
    state = load_state()
    today = moment.date().isoformat()
    if state.get("lastRun") == today:
        return False
    if state.get("attemptDate") == today and int(state.get("attempts") or 0) >= MAX_ATTEMPTS:
        return False
    last = state.get("lastAttempt")
    if last:
        try:
            previous = dt.datetime.strptime(last, "%Y-%m-%d %H:%M")
            if (moment - previous).total_seconds() < COOLDOWN:
                return False
        except Exception:
            pass
    return True


def run_if_due() -> None:
    if due():
        run()
