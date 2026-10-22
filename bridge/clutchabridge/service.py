"""The poll loop: check the mailbox, hand new messages to the agent, reply."""

from __future__ import annotations

import os
import threading
import time

from . import agent
from . import cleanup
from . import commands
from . import config as cfg
from . import mail
from .state import STATE

POLL_MIN = cfg.POLL_MIN
POLL_MAX = cfg.POLL_MAX
# A mailbox blip on the provider's side outlasts a couple of seconds: 139's POP3
# answers `-ERR System error` for tens of seconds at a time while it decides to
# work again. Three attempts 3s apart gave up inside the blip; these three span
# about half a minute.
RETRY_DELAYS = (0, 5, 15)

DEFAULT_REPLY_MAX_CHARS = 6000
REPLY_MAX_LIMIT = 20000


def reply_limit() -> int:
    try:
        value = int(cfg.session().get("replyMaxChars") or DEFAULT_REPLY_MAX_CHARS)
    except Exception:
        value = DEFAULT_REPLY_MAX_CHARS
    return max(500, min(REPLY_MAX_LIMIT, value))


def _keep_long_reply(text: str) -> str | None:
    """A cut reply is not a lost reply: keep the whole thing on disk."""
    directory = os.path.join(cfg.STATE_DIR, "replies")
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, time.strftime("%Y%m%d-%H%M%S") + ".txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(path, 0o600)
        return path
    except Exception:
        return None


def clamp_interval(seconds: int) -> int:
    return max(POLL_MIN, min(POLL_MAX, int(seconds)))


def poll_once(trigger: str) -> None:
    if not cfg.is_configured():
        STATE.add("poll", "bridge is not configured yet — see the Setup tab", "warn")
        return
    with STATE.lock:
        if STATE.polling:
            return
        STATE.polling = True
    try:
        STATE.add("poll", f"checking inbox ({trigger})")

        messages = None
        last_error: Exception | None = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            if delay:
                time.sleep(delay)
            try:
                messages = mail.fetch_new_messages()
                break
            except Exception as error:
                last_error = error
                if attempt < len(RETRY_DELAYS):
                    STATE.add(
                        "poll",
                        f"mailbox busy, retrying ({attempt}/{len(RETRY_DELAYS) - 1}): {error}",
                        "warn",
                    )

        if messages is None:
            STATE.bump("errors")
            with STATE.lock:
                STATE.last_poll_result = f"error: {last_error}"
                STATE.last_poll_at = time.time()
            STATE.add("error", f"mailbox check failed: {last_error}", "error")
            return

        STATE.bump("polls")
        with STATE.lock:
            STATE.last_poll_at = time.time()

        if not messages:
            with STATE.lock:
                STATE.last_poll_result = "no new messages"
            STATE.add("poll", "no new messages")
            return

        with STATE.lock:
            STATE.last_poll_result = f"{len(messages)} new message(s)"

        for incoming in messages:
            STATE.bump("received")
            STATE.add("receive", f"from {incoming['from']}: “{incoming['plaintext']}”")
            # Control mail is answered here, not by the model: a ping should
            # come back in seconds, and it must not cost a turn of context.
            answer = commands.handle(incoming["plaintext"])
            if answer is not None:
                STATE.add("receive", f"command {commands.split(incoming['plaintext'])[0]}")
            else:
                answer = agent.reply(incoming["plaintext"])
            if not answer:
                continue

            # A tool-heavy turn can dump tens of kilobytes; armor adds a third
            # on top and the provider has an opinion about that. Cut, say so,
            # and leave the full text on disk.
            limit = reply_limit()
            if len(answer) > limit:
                original = len(answer)
                kept = _keep_long_reply(answer)
                tail = f"\n\n[… cut at {limit} characters by the bridge"
                tail += f". Full text on the Mac: {kept}]" if kept else ".]"
                answer = answer[:limit].rstrip() + tail
                STATE.add("service", f"reply cut to {limit} characters (was {original})", "warn")

            try:
                mail.send_message(answer)
                STATE.bump("replied")
                STATE.last_reply_at = time.time()
                STATE.add("send", f"sent to {cfg.address()}: “{answer}”")
            except Exception as error:
                STATE.bump("errors")
                STATE.add("error", f"send failed: {error}", "error")

        # After the mail is handled, not before: a cleanup that runs first could
        # delete the letter this cycle was supposed to answer.
        try:
            cleanup.run_if_due()
        except Exception as error:
            STATE.add("cleanup", f"scheduled cleanup failed: {error}", "warn")
    finally:
        with STATE.lock:
            STATE.polling = False


def poll_loop() -> None:
    interval = int(cfg.poll_cfg().get("intervalSeconds") or cfg.DEFAULT_POLL_SECONDS)
    STATE.add("service", f"bridge started · polling every {interval}s")
    while True:
        if not cfg.is_configured() or not cfg.poll_cfg().get("enabled", True):
            with STATE.lock:
                STATE.next_poll_at = None
            STATE.wake.wait(5)
            STATE.wake.clear()
            continue

        poll_once("scheduled")

        interval = int(cfg.poll_cfg().get("intervalSeconds") or cfg.DEFAULT_POLL_SECONDS)
        with STATE.lock:
            STATE.next_poll_at = time.time() + interval
        STATE.wake.wait(interval)
        STATE.wake.clear()


def start() -> threading.Thread:
    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()
    return thread


def poll_now() -> None:
    threading.Thread(target=poll_once, args=("manual",), daemon=True).start()
