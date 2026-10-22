#!/usr/bin/env python3
"""Clutcha Bridge — entry point.

    python3 clutcha_bridge.py

The bridge is transport only: it moves encrypted mail between the Clutcha app
and an agent session. The web UI is on http://127.0.0.1:8787/ (Status, Setup,
Session) and never leaves loopback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import webbrowser

BANNER = """
  Clutcha Bridge {version}
  ─────────────────────────────────────────────
  Status  http://127.0.0.1:{port}/
  Setup   http://127.0.0.1:{port}/setup
  Session http://127.0.0.1:{port}/session

  Keep this window open. Close it (or press Ctrl-C) to stop.
"""


def _fail(message: str, hint: str = "") -> None:
    print(f"\n  {message}\n", file=sys.stderr)
    if hint:
        print(f"  {hint}\n", file=sys.stderr)
    sys.exit(1)


def _check_dependencies() -> None:
    missing = []
    for module, package in (("cryptography", "cryptography"), ("qrcode", "qrcode")):
        try:
            __import__(module)
        except Exception:
            missing.append(package)
    if missing:
        _fail(
            "Missing Python package(s): " + ", ".join(missing),
            "Run install.command first, or:  pip3 install --user " + " ".join(missing),
        )


def _is_bridge(port: int) -> bool:
    """True when a Clutcha Bridge already answers on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "version" in payload and "configured" in payload
    except Exception:
        return False


def ensure_agent_folder() -> None:
    """The agent runs in its own folder; create it rather than fail on first run.

    `config` is imported inside main(), so this asks for it here too.
    """
    from clutchabridge import config

    folder = config.default_cwd()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as error:
        print(f"could not create {folder}: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clutcha Bridge")
    parser.add_argument("--port", type=int, default=0, help="override the port from config.json")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args()

    _check_dependencies()

    from clutchabridge import __version__, config, crypto, server, service
    from clutchabridge.state import STATE

    if args.port:
        config.CONFIG.setdefault("server", {})["port"] = args.port
        config.save_config()

    wanted = int((config.CONFIG.get("server") or {}).get("port") or 8787)

    # One bridge per config: a second instance would poll the same mailbox with
    # the same cursor and answer every message twice.
    if _is_bridge(wanted):
        url = f"http://127.0.0.1:{wanted}/"
        print(f"\n  Clutcha Bridge is already running: {url}\n")
        if not args.no_browser:
            webbrowser.open(url)
        return

    crypto.ensure_identities()
    crypto.refresh_conversation_key()
    ensure_agent_folder()

    if not config.is_configured():
        STATE.add("service", "bridge starting (mailbox not configured yet — see the Setup tab)", "warn")
    else:
        STATE.add("service", "bridge starting")
    session = config.session()
    STATE.add(
        "service",
        f"agent: {config.monkey().get('name')} · session={session.get('sessionId')} · "
        f"tools={session.get('tools')} · harness={session.get('harness')}",
    )

    try:
        httpd, port = server.start()
    except Exception as error:
        _fail(f"Could not start the web UI: {error}", "Another program may be using ports 8787-8796.")

    print(BANNER.format(version=__version__, port=port))
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")

    thread = service.start()
    try:
        while thread.is_alive():
            thread.join(1)
    except KeyboardInterrupt:
        print("\n  stopping…", file=sys.stderr)
        os._exit(0)


if __name__ == "__main__":
    main()
