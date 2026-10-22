"""Mail transport: read the shared mailbox, decrypt, and send replies.

POP3 is the default (some providers have no IMAP). POP3 has no server-side
unread flag, so a local UID cursor keeps the back log from being re-examined.
"""

from __future__ import annotations

import imaplib
import json
import os
import poplib
import smtplib
import ssl
import uuid
from email import message_from_bytes
from email.header import Header, decode_header, make_header
from email.message import Message
from email.utils import formatdate

from . import config as cfg
from . import crypto
from . import template
from .state import STATE

# Written by us, and (for one version) by the old bridge. Both are read, so a
# mailbox may hold letters from either side of the rename.
REPLY_HEADER = "X-Clutcha-Reply"
LEGACY_REPLY_HEADERS = ("X-VMessager-Reply",)
CURSOR_PATH = os.path.join(cfg.STATE_DIR, ".pop3_cursor.json")
# IMAP has a server-side seen flag, so it needs its own "I have looked at this
# mailbox before" marker rather than a UID list.
IMAP_MARK = os.path.join(cfg.STATE_DIR, ".imap_seen")
TIMEOUT = 30


def error_text(error: Exception) -> str:
    """`b'-ERR System error'` -> `-ERR System error`.

    poplib reports the server's line as raw bytes, and a status message does not
    need the quoting.
    """
    text = str(error)
    if text.startswith("b'") and text.endswith("'"):
        text = text[2:-1]
    elif text.startswith('b"') and text.endswith('"'):
        text = text[2:-1]
    return text.strip()


def step(name: str, call):
    """Run one POP3 command and say which one failed.

    "connection refused" and "uidl: -ERR System error" are different problems,
    and the log line is the only place the difference shows up.
    """
    try:
        return call()
    except Exception as error:
        raise RuntimeError(f"{name}: {error_text(error)}") from error


def decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


# --------------------------------------------------------------------------- #
# Cursor
# --------------------------------------------------------------------------- #

def load_cursor() -> set[str]:
    try:
        with open(CURSOR_PATH, "r", encoding="utf-8") as handle:
            return set(json.load(handle))
    except Exception:
        return set()


def _save_cursor(uids: set[str]) -> None:
    try:
        with open(CURSOR_PATH, "w", encoding="utf-8") as handle:
            json.dump(sorted(uids)[-5000:], handle)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Inbound
# --------------------------------------------------------------------------- #

def _handle_message(message: Message, uid: str) -> dict | None:
    sender = decode(message.get("From"))
    if message.get(REPLY_HEADER) or any(message.get(header) for header in LEGACY_REPLY_HEADERS):
        STATE.add("receive", f"skipped (our own reply): {sender}")
        return None
    only_from = cfg.me_mail().get("address")
    if only_from and only_from not in sender and not (cfg.monkey().get("mail") or {}).get("mode") == "own":
        return None

    raw_body = message.get_payload(decode=True)
    if raw_body is None:
        return None
    body = raw_body.decode(message.get_content_charset() or "utf-8", "replace")
    envelope = crypto.unarmor(body)
    if envelope is None:
        return None

    try:
        plaintext = crypto.open_envelope(envelope)
    except Exception as error:
        STATE.add("error", f"decrypt failed from {sender}: {error}", "error")
        STATE.bump("errors")
        return None

    if plaintext is None:
        adopted = crypto.adopt_peer_key(envelope, STATE)
        if adopted is None:
            return None
        conversation, _ = adopted
        parsed = crypto.parse_envelope(envelope)
        header = envelope[: parsed["header_length"]]
        payload = envelope[parsed["header_length"]:]
        try:
            plaintext = crypto.ChaCha20Poly1305(conversation).decrypt(
                header[21:33], payload[:-16] + payload[-16:], header
            ).decode("utf-8")
        except Exception as error:
            STATE.add("error", f"decrypt after adoption failed: {error}", "error")
            STATE.bump("errors")
            return None

    return {
        "uid": uid,
        "from": sender,
        "subject": decode(message.get("Subject")),
        "plaintext": plaintext,
    }


def fetch_new_messages() -> list[dict]:
    inbox = cfg.mailbox()["inbox"]
    if inbox.get("protocol", "pop3") == "imap":
        return _fetch_imap(inbox)
    return _fetch_pop3(inbox)


def _first_look_imap(client) -> bool:
    """Mark everything already in the mailbox as seen, without answering it.

    A new install knows nothing about the past, and the past in an IMAP mailbox
    is UNSEEN mail. Answering it would mean replying to a conversation the user
    had with a different bridge, or with no bridge at all.
    """
    if os.path.exists(IMAP_MARK):
        return False
    status, data = client.search(None, "UNSEEN")
    if status != "OK":
        return False
    uids = data[0].split()
    for uid in uids:
        client.store(uid, "+FLAGS", "\\Seen")
    try:
        with open(IMAP_MARK, "w", encoding="utf-8") as handle:
            handle.write("seen\n")
    except Exception:
        pass
    STATE.add("poll", f"first run: {len(uids)} old message(s) marked seen, none answered")
    return True


def _fetch_imap(inbox: dict) -> list[dict]:
    client = imaplib.IMAP4_SSL(inbox["host"], int(inbox["port"]), timeout=TIMEOUT)
    try:
        client.login(inbox["username"], inbox["token"])
        client.select("INBOX")
        if _first_look_imap(client):
            return []
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            return []
        results: list[dict] = []
        for uid in data[0].split():
            status, payload = client.fetch(uid, "(RFC822)")
            if status != "OK":
                continue
            message = message_from_bytes(payload[0][1])
            got = _handle_message(message, uid.decode())
            client.store(uid, "+FLAGS", "\\Seen")
            if got:
                results.append(got)
        return results
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _fetch_pop3(inbox: dict) -> list[dict]:
    client = step(
        "connect",
        lambda: poplib.POP3_SSL(inbox["host"], int(inbox["port"]), timeout=TIMEOUT),
    )
    try:
        step("login", lambda: (client.user(inbox["username"]), client.pass_(inbox["token"])))
        response, lines, _ = step("uidl", client.uidl)
        if not response.startswith(b"+OK"):
            return []

        if not os.path.exists(CURSOR_PATH):
            # Same rule for POP3, which has no seen flag to rely on: everything
            # in the mailbox predates this bridge, so record it and answer none
            # of it. From here on the cursor is the record of what arrived.
            everything = [
                line.decode().split()[1]
                for line in lines
                if len(line.decode().split()) == 2
            ]
            _save_cursor(set(everything))
            STATE.add(
                "poll",
                f"first run: {len(everything)} old message(s) recorded, none answered",
            )
            return []

        done = load_cursor()
        numbered = []
        for line in lines:
            parts = line.decode().split()
            if len(parts) == 2:
                numbered.append((int(parts[0]), parts[1]))
        catalogue = {uid for _, uid in numbered}
        limit = int(cfg.poll_cfg().get("maxScan") or 20)
        candidates = [pair for pair in sorted(numbered, reverse=True) if pair[1] not in done][:limit]

        STATE.add("poll", f"pop3: {len(catalogue)} in mailbox, examining {len(candidates)}")
        results: list[dict] = []
        for number, uid in candidates:
            try:
                _, raw_lines, _ = step(f"fetch {number}", lambda: client.retr(number))
            except Exception as error:
                # One unreadable message is not a broken mailbox: say so and
                # keep the rest of the batch.
                STATE.add("poll", f"skipped a message: {error_text(error)}", "warn")
                continue
            got = _handle_message(message_from_bytes(b"\r\n".join(raw_lines)), uid)
            if got:
                results.append(got)
        _save_cursor(done | catalogue)
        return results
    finally:
        try:
            client.quit()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Outbound
# --------------------------------------------------------------------------- #

def _encoded_subject(value: str) -> str:
    """RFC 2047 only when needed: a raw UTF-8 header shows up as mojibake, and
    an encoded pure-ASCII header looks like bulk mail."""
    return value if value.isascii() else Header(value, "utf-8").encode()


def build_body(armored: str) -> str:
    return template.body(cfg.mail_template(), armored, cfg.monkey().get("name") or "Monkey")


def send_message(text: str) -> None:
    smtp_cfg = cfg.mailbox()["smtp"]
    to = cfg.address()
    letter = cfg.mail_template()
    body = build_body(crypto.armor(crypto.seal_envelope(text)))
    message = (
        f"From: Clutcha Bridge <{smtp_cfg['username']}>\r\n"
        f"To: {to}\r\n"
        f"Subject: {_encoded_subject(template.subject(letter))}\r\n"
        f"Date: {formatdate(localtime=True)}\r\n"
        f"Message-ID: <{uuid.uuid4()}@clutcha>\r\n"
        f"X-Clutcha: 1\r\n"
        f"{REPLY_HEADER}: 1\r\n"
        f"X-VMessager-Reply: 1\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset=\"utf-8\"\r\n"
        f"Content-Transfer-Encoding: 8bit\r\n\r\n{body}\r\n"
    )

    if smtp_cfg.get("useSSL"):
        client = smtplib.SMTP_SSL(
            smtp_cfg["host"], int(smtp_cfg["port"]), timeout=TIMEOUT,
            context=ssl.create_default_context(),
        )
    else:
        client = smtplib.SMTP(smtp_cfg["host"], int(smtp_cfg["port"]), timeout=TIMEOUT)
    try:
        client.ehlo()
        if smtp_cfg.get("starttls"):
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        client.login(smtp_cfg["username"], smtp_cfg["token"])
        client.sendmail(smtp_cfg["username"], [to], message.encode("utf-8"))
    finally:
        try:
            client.quit()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Connection test (used by the Bridge page)
# --------------------------------------------------------------------------- #

def test_credentials(payload: dict) -> dict:
    """payload: {address, inbox:{...}, smtp:{...}} with plain tokens."""
    inbox = payload.get("inbox") or {}
    smtp_cfg = payload.get("smtp") or {}
    problems: list[str] = []
    steps: list[str] = []

    try:
        if inbox.get("protocol", "pop3") == "imap":
            client = imaplib.IMAP4_SSL(inbox["host"], int(inbox["port"]), timeout=TIMEOUT)
            client.login(inbox["username"], inbox["token"])
            client.select("INBOX")
            client.logout()
        else:
            client = poplib.POP3_SSL(inbox["host"], int(inbox["port"]), timeout=TIMEOUT)
            client.user(inbox["username"])
            client.pass_(inbox["token"])
            count, _ = client.stat()
            steps.append(f"inbox ok · {count} messages")
            client.quit()
        if not steps:
            steps.append("inbox ok")
    except Exception as error:
        problems.append(f"inbox: {error}")

    try:
        if smtp_cfg.get("useSSL"):
            client = smtplib.SMTP_SSL(
                smtp_cfg["host"], int(smtp_cfg["port"]), timeout=TIMEOUT,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(smtp_cfg["host"], int(smtp_cfg["port"]), timeout=TIMEOUT)
        client.ehlo()
        if smtp_cfg.get("starttls"):
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        client.login(smtp_cfg["username"], smtp_cfg["token"])
        steps.append("smtp login ok")
        client.quit()
    except Exception as error:
        problems.append(f"smtp: {error}")

    return {"ok": not problems, "problems": problems, "steps": steps}
