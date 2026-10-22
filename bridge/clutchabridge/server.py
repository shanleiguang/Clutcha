"""HTTP layer: three pages and a small JSON API. Loopback only."""

from __future__ import annotations

import json
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import __version__
from . import agent
from . import cleanup
from . import config as cfg
from . import crypto
from . import mail
from . import service
from . import template as letter_template
from .state import STATE
from .web import pages

TEST_LETTER_COOLDOWN = 20.0
_LAST_TEST_LETTER = [0.0]


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "on", "yes")


def _pick(payload: dict, key: str, current: str) -> str:
    """Never clobber a stored value with a blank field."""
    value = payload.get(key)
    if value is None:
        return current
    value = str(value).strip()
    return value if value else current


def _split_lines(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


class Handler(BaseHTTPRequestHandler):
    server_version = f"ClutchaBridge/{__version__}"

    def log_message(self, *args):
        pass

    # -- plumbing ----------------------------------------------------------- #

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    # -- GET ---------------------------------------------------------------- #

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            return self._get(path)
        except Exception as error:
            # A local tool should say what broke, not drop the connection.
            body = (f"<!doctype html><meta charset='utf-8'><title>Error</title>"
                    f"<body style='font:15px -apple-system;padding:40px;line-height:1.6'>"
                    f"<h2>Something broke while rendering {path}</h2>"
                    f"<pre style='white-space:pre-wrap'>{escape(str(error))}</pre>"
                    f"<p><a href='/'>Back to Status</a></p></body>")
            return self._send(500, body.encode("utf-8"), "text/html; charset=utf-8")

    def _get(self, path: str):
        if path in ("/", "/index.html"):
            return self._send(200, pages.status_page().encode("utf-8"), "text/html; charset=utf-8")
        if path == "/setup":
            return self._send(200, pages.setup_page().encode("utf-8"), "text/html; charset=utf-8")
        if path == "/session":
            return self._send(200, pages.session_page().encode("utf-8"), "text/html; charset=utf-8")
        # The old tab names, kept so a bookmark does not 404.
        if path == "/bridge":
            return self._redirect("/setup")
        if path == "/monkey":
            return self._redirect("/session")

        if path == "/api/status":
            return self._json(STATE.snapshot())
        if path == "/api/live":
            return self._json(pages.status_live())
        if path == "/api/session":
            session = cfg.session()
            return self._json({
                "session": session,
                "command": agent.display_command(session, "{message}"),
                "info": agent.session_info(session),
            })
        if path == "/api/letter":
            return self._json(letter_template.preview(cfg.mail_template(), cfg.monkey().get("name") or "Monkey"))
        if path in ("/api/pairing.png", "/api/pairing.svg"):
            if not cfg.is_configured():
                return self._send(404, b"not configured", "text/plain")
            image = crypto.pairing_image()
            if image is None:
                return self._send(
                    500,
                    b"could not render a QR code (is the qrcode package installed?)",
                    "text/plain",
                )
            body, content_type = image
            return self._send(200, body, content_type)
        if path == "/api/pairing":
            payload = crypto.build_pairing_payload()
            if payload is None:
                return self._json({"error": "not configured"}, 404)
            return self._json({"pairing": payload})
        return self._send(404, b"not found", "text/plain")

    # -- POST --------------------------------------------------------------- #

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if path == "/api/me":
                return self._json(self._save_mailbox(self._body()))
            if path == "/api/cleanup":
                return self._json(self._save_cleanup(self._body()))
            if path == "/api/ui-lang":
                return self._json(self._save_lang(self._body()))
            if path in ("/api/poll-config", "/api/settings"):
                return self._json(self._save_poll(self._body()))
            if path == "/api/poll-now":
                service.poll_now()
                return self._json({"ok": True, "message": "Checking the mailbox…"})
            if path == "/api/test-mailbox":
                self._body()
                return self._json(self._test_mailbox())
            if path == "/api/letter":
                return self._json(self._save_letter(self._body()))
            if path == "/api/letter/preview":
                return self._json(self._preview_letter(self._body()))
            if path == "/api/letter/test":
                self._body()
                return self._json(self._send_test_letter())
            if path == "/api/session":
                return self._json(self._save_session(self._body()))
            if path == "/api/session/preview":
                return self._json(self._preview_session(self._body()))
            if path == "/api/session/check-cwd":
                return self._json(self._check_cwd(self._body()))
            if path == "/api/session/test":
                self._body()
                return self._json(self._test_session())
            if path == "/api/session/reset":
                self._body()
                result = agent.archive_session(cfg.session())
                if result.get("ok"):
                    STATE.add("service", f"session archived: {len(result.get('archived') or [])} file(s)")
                    return self._json({"ok": True, "message": "Session archived", "reload": True})
                return self._json({"ok": False, "error": result.get("error") or "failed"}, 400)
        except Exception as error:
            return self._json({"ok": False, "error": str(error)}, 400)
        return self._send(404, b"not found", "text/plain")

    # -- mailbox ------------------------------------------------------------ #

    def _save_mailbox(self, payload: dict) -> dict:
        mail_cfg = cfg.me_mail()
        # The Name on this card is the agent's alias — the phone prints it above
        # replies. The phone's own identity name is not something the page asks
        # for; "Me" stays as the pairing payload's label.
        if payload.get("agent_name") is not None:
            alias = str(payload.get("agent_name") or "").strip()
            cfg.monkey()["name"] = alias or "Clutcha"
        previous_address = mail_cfg.get("address") or ""
        mail_cfg["address"] = _pick(payload, "address", previous_address)
        address = mail_cfg["address"]

        # The page does not ask for a username: the login name is the address
        # for every provider this targets. Keep a hand-written username from an
        # older config, but follow the address if the two had been the same.
        def login_name(block: dict, fallback: str) -> str:
            current = (block.get("username") or "").strip()
            if not current or current == previous_address:
                return address or current or fallback
            return current

        inbox = mail_cfg.setdefault("inbox", {})
        inbox["protocol"] = _pick(payload, "inbox_protocol", inbox.get("protocol") or "pop3")
        inbox["host"] = _pick(payload, "inbox_host", inbox.get("host") or "")
        inbox["port"] = int(_pick(payload, "inbox_port", str(inbox.get("port") or 995)))
        inbox["username"] = login_name(inbox, address)
        # One credential, not two: providers issue a single authorization code
        # per account and use it for POP3/IMAP and SMTP alike. The older fields
        # are still accepted so a hand-written request keeps working.
        shared_token = payload.get("mail_token", payload.get("inbox_token"))
        inbox["token"] = _pick({"t": shared_token}, "t", inbox.get("token") or "")
        inbox["useSSL"] = _truthy(payload.get("inbox_ssl", inbox.get("useSSL", True)))
        inbox["starttls"] = _truthy(payload.get("inbox_starttls", inbox.get("starttls", False)))

        smtp = mail_cfg.setdefault("smtp", {})
        smtp["host"] = _pick(payload, "smtp_host", smtp.get("host") or "")
        smtp["port"] = int(_pick(payload, "smtp_port", str(smtp.get("port") or 465)))
        smtp["username"] = login_name(smtp, address or inbox["username"])
        smtp["token"] = _pick({"t": payload.get("mail_token", payload.get("smtp_token"))}, "t",
                              smtp.get("token") or inbox.get("token") or "")
        smtp["useSSL"] = _truthy(payload.get("smtp_ssl", smtp.get("useSSL", True)))
        smtp["starttls"] = _truthy(payload.get("smtp_starttls", smtp.get("starttls", False)))

        cfg.save_config()
        crypto.ensure_identities()
        crypto.refresh_conversation_key()
        STATE.add("service", "mailbox settings saved")
        STATE.wake.set()
        return {"ok": True, "message": "Mailbox saved", "reload": True}

    def _save_cleanup(self, payload: dict) -> dict:
        block = cfg.cleanup_cfg()
        if "enabled" in payload:
            block["enabled"] = _truthy(payload.get("enabled"))
        if payload.get("hour") not in (None, ""):
            wanted = int(payload["hour"])
            block["hour"] = wanted if wanted in cleanup.HOURS else cleanup.HOURS[1]
        cfg.save_config()
        STATE.add("service", f"cleanup {'on' if block.get('enabled') else 'off'} at {block.get('hour')}:00")
        return {"ok": True, "message": "Cleanup saved", "reload": True}

    def _save_lang(self, payload: dict) -> dict:
        wanted = str(payload.get("lang") or "").strip().lower()
        if wanted not in ("en", "zh"):
            return {"ok": False, "error": "lang must be en or zh"}
        cfg.ui_cfg()["lang"] = wanted
        cfg.save_config()
        return {"ok": True, "message": "中文" if wanted == "zh" else "English", "reload": True}

    def _save_poll(self, payload: dict) -> dict:
        poll = cfg.poll_cfg()
        if payload.get("intervalSeconds") not in (None, ""):
            poll["intervalSeconds"] = service.clamp_interval(int(payload["intervalSeconds"]))
        if payload.get("maxScan") not in (None, ""):
            poll["maxScan"] = max(1, min(200, int(payload["maxScan"])))
        if "enabled" in payload:
            poll["enabled"] = _truthy(payload["enabled"])
        cfg.save_config()
        STATE.add("service", "polling settings saved")
        STATE.wake.set()
        return {"ok": True, "message": "Polling saved", "reload": True}

    def _test_mailbox(self) -> dict:
        mail_cfg = cfg.me_mail()
        result = mail.test_credentials(
            {"address": mail_cfg.get("address"), "inbox": mail_cfg.get("inbox"), "smtp": mail_cfg.get("smtp")}
        )
        if result["ok"]:
            STATE.add("service", "mailbox test ok")
            return {"ok": True, "message": "Connection ok", "output": "\n".join(result["steps"])}
        STATE.add("service", "mailbox test failed: " + "; ".join(result["problems"]), "error")
        return {
            "ok": False,
            "error": "; ".join(result["problems"]),
            "output": "\n".join(result["steps"] + result["problems"]),
        }

    # -- letter ------------------------------------------------------------- #

    def _letter_from_payload(self, payload: dict, base: dict | None = None) -> dict:
        letter = json.loads(json.dumps(base or cfg.mail_template()))
        if payload.get("lang"):
            letter["lang"] = str(payload["lang"])
        if "vary" in payload:
            letter["vary"] = _truthy(payload["vary"])
        for key in ("subject", "body"):
            block = letter.setdefault(key, {})
            for lang in letter_template.LANGS:
                field = f"{key}_{lang}"
                if field in payload:
                    block[lang] = str(payload[field] or "").strip()
        for key in ("greeting", "closing"):
            block = letter.setdefault(key, {})
            for lang in letter_template.LANGS:
                field = f"{key}_{lang}"
                if field in payload:
                    block[lang] = _split_lines(payload[field])
        return letter

    def _save_letter(self, payload: dict) -> dict:
        candidate = self._letter_from_payload(payload)
        found = letter_template.problems(candidate)
        if found:
            STATE.add("service", "letter not saved: " + "; ".join(found), "warn")
            return {"ok": False, "error": " ".join(found)}
        cfg.CONFIG["mail"] = candidate
        cfg.save_config()
        STATE.add("service", "letter settings saved")
        return {"ok": True, "message": "Letter saved", "reload": True}

    def _preview_letter(self, payload: dict) -> dict:
        candidate = self._letter_from_payload(payload)
        preview = letter_template.preview(candidate, cfg.monkey().get("name") or "Monkey")
        body = f"Subject: {preview['subject']}\n\n{preview['body']}"
        found = preview["problems"] or preview["warnings"]
        if found:
            body += "\n---\n" + "\n".join(found)
        return {"ok": True, "message": "Preview", "output": body}

    def _send_test_letter(self) -> dict:
        now = time.time()
        if now - _LAST_TEST_LETTER[0] < TEST_LETTER_COOLDOWN:
            return {"ok": False, "error": "A test letter was just sent — wait a moment."}
        if not cfg.is_configured():
            return {"ok": False, "error": "Configure the mailbox first."}
        _LAST_TEST_LETTER[0] = now
        mail.send_message("Test letter from Clutcha Bridge. If you can read this in the app, the "
                          "mailbox, the keys and the letter all work.")
        STATE.add("send", f"test letter sent to {cfg.address()}")
        return {"ok": True, "message": "Test letter sent — delivery can take about a minute."}

    # -- session ------------------------------------------------------------ #

    def _session_from_payload(self, payload: dict) -> dict:
        session = json.loads(json.dumps(cfg.session()))
        session["harness"] = _pick(payload, "harness", session.get("harness") or "pi")
        session["mode"] = "raw" if _pick(payload, "mode", session.get("mode") or "simple") == "raw" else "simple"
        session["sessionId"] = _pick(payload, "sessionId", session.get("sessionId") or "clutcha-main")
        if "cwd" in payload:
            session["cwd"] = str(payload.get("cwd") or "").strip()
        # Blank is meaningful for both: "pi's default model", "pi's thinking".
        if "model" in payload:
            session["model"] = str(payload.get("model") or "").strip()
        if "thinking" in payload:
            session["thinking"] = str(payload.get("thinking") or "").strip()
        session["tools"] = "on" if _truthy(payload.get("tools")) else "off"
        if "systemPrompt" in payload:
            session["systemPrompt"] = str(payload.get("systemPrompt") or "")
        if "fallback" in payload:
            session["fallback"] = str(payload.get("fallback") or "")
        if payload.get("timeoutSeconds") not in (None, ""):
            session["timeoutSeconds"] = max(10, min(3600, int(payload["timeoutSeconds"])))
        if payload.get("replyMaxChars") not in (None, ""):
            session["replyMaxChars"] = max(500, min(service.REPLY_MAX_LIMIT, int(payload["replyMaxChars"])))
        if payload.get("command"):
            session["command"] = str(payload["command"])
        if session["mode"] == "simple":
            session["command"] = agent.build_command(session)
        # Fields the bridge no longer manages; keep migrated configs tidy.
        for retired in ("toolsList", "contextFiles", "extraArgs"):
            session.pop(retired, None)
        return session

    def _save_session(self, payload: dict) -> dict:
        candidate = self._session_from_payload(payload)
        placement = agent.check_cwd(candidate.get("cwd") or "")
        if not placement["ok"]:
            return {"ok": False, "error": f"{placement['error']} ({placement['path']})"}
        try:
            agent.render_command(candidate, "ping")
        except Exception as error:
            return {"ok": False, "error": f"Command is not usable: {error}"}

        cfg.CONFIG.setdefault("monkey", {})["session"] = candidate
        cfg.save_config()
        STATE.add("service", f"session saved (tools: {candidate.get('tools')}, mode: {candidate.get('mode')})")
        return {"ok": True, "message": "Session saved", "reload": True}

    def _preview_session(self, payload: dict) -> dict:
        candidate = self._session_from_payload(payload) if payload else cfg.session()
        return {"ok": True, "message": "Command", "output": agent.display_command(candidate, "Hello from the app")}

    def _check_cwd(self, payload: dict) -> dict:
        result = agent.check_cwd(payload.get("cwd") or "")
        if not result["ok"]:
            return {"ok": False, "error": result["error"], "output": f"{result['path']}\n{result['error']}"}
        lines = [result["path"], "exists · folder"]
        lines.append("writable" if result["writable"] else "not writable (the agent may fail to write files)")
        if result["contextFiles"]:
            lines.append("contains " + ", ".join(result["contextFiles"]) +
                         " — read only if the context-files box is ticked")
        return {"ok": True, "message": "Folder ok", "output": "\n".join(lines)}

    def _test_session(self) -> dict:
        session = cfg.session()
        started = time.time()
        try:
            argv = agent.render_command(session, "Reply with the single word: pong")
            output = agent.invoke(argv, session)
        except Exception as error:
            return {"ok": False, "error": str(error), "output": str(error)}
        elapsed = time.time() - started
        return {
            "ok": True,
            "message": f"Session replied in {elapsed:.1f}s",
            "output": output or "(empty)",
        }


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #

def _bind(host: str, start_port: int, attempts: int = 10) -> ThreadingHTTPServer:
    last_error: Exception | None = None
    for offset in range(attempts):
        port = start_port + offset
        try:
            return ThreadingHTTPServer((host, port), Handler)
        except OSError as error:
            last_error = error
            continue
    raise RuntimeError(f"could not bind {host}:{start_port}-{start_port + attempts - 1}: {last_error}")


def start() -> tuple[ThreadingHTTPServer, int]:
    server_cfg = cfg.CONFIG.get("server") or {}
    host = server_cfg.get("host") or "127.0.0.1"
    wanted = int(server_cfg.get("port") or 8787)
    httpd = _bind(host, wanted)
    port = httpd.server_address[1]
    if port != wanted:
        server_cfg["port"] = port
        cfg.CONFIG["server"] = server_cfg
        cfg.save_config()
        STATE.add("service", f"port {wanted} was busy — using {port}", "warn")
    STATE.add("service", f"web UI on http://{host}:{port}/")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port
