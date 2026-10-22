"""The agent session.

The bridge owns no conversation state. It renders one command line, runs it,
and returns its stdout. History, tools and memory belong to the runtime, so
the session is fully described by: command + session id + working directory.

Two ways to describe that command line:

    mode = "simple"   the form fields below build it (the normal case)
    mode = "raw"      the string is hand-written; the form only displays it

Placeholders usable in the command:
    {sessionId}  {message}  {systemPrompt}  {cwd}
Everything else is passed through untouched (model, thinking, tools...).
"""

from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
import time

from . import config as cfg
from .state import STATE

PLACEHOLDERS = ("sessionId", "message", "systemPrompt", "cwd")

THINKING_LEVELS = ("", "off", "minimal", "low", "medium", "high", "xhigh", "max")

# The bridge deliberately sets almost nothing: the session is the user's, made
# with pi on their own machine. The single exception is tools, because a paired
# phone would otherwise inherit whatever the interactive configuration allows.
_FLAGS_WITH_VALUE = {
    "--session-id", "--model", "--thinking", "--append-system-prompt", "--system-prompt",
}
_FLAGS_BARE = {"-p", "--print", "-nt", "--no-tools"}


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #

def system_prompt(session: dict) -> str:
    """Exactly what the user typed, nothing appended.

    There used to be a second paragraph here teaching the agent to emit
    `[[poll=N]]`, which the bridge then obeyed. That handed the model a vote on
    the bridge's own schedule through a channel with no authentication: the
    directive is model output, and model output is steered by everything the
    model reads. The interval is set by the person on the Setup tab, or by a
    paired phone through an encrypted control letter.
    """
    return (session.get("systemPrompt") or "").strip()


def build_command(session: dict) -> str:
    """Render the few fields the bridge owns into the pi command line."""
    parts = ["pi", "-p", "--session-id", "{sessionId}"]

    model = (session.get("model") or "").strip()
    if model:
        parts += ["--model", model]
    if (session.get("tools") or "off").lower() != "on":
        parts.append("-nt")
    thinking = (session.get("thinking") or "").strip()
    if thinking:
        parts += ["--thinking", thinking]
    if system_prompt(session):
        parts += ["--append-system-prompt", "{systemPrompt}"]

    parts.append("{message}")
    return " ".join(parts)


def parse_command(command: str) -> dict:
    """Best-effort reverse of build_command, for showing a migrated config.

    `modelled` is False when the command uses anything the form does not know
    (a tool allowlist, extensions, extra prompts) — the caller then keeps the
    raw command instead of rewriting it and silently dropping those flags.
    """
    out: dict = {"tools": "on", "thinking": "", "model": "", "modelled": True}
    try:
        tokens = shlex.split(command or "")
    except Exception:
        out["modelled"] = False
        return out

    index = 0
    unknown: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token in _FLAGS_WITH_VALUE:
            value = tokens[index + 1] if index + 1 < len(tokens) else ""
            if token == "--thinking":
                out["thinking"] = value
            elif token == "--model":
                out["model"] = value
            index += 2
            continue
        if token in _FLAGS_BARE:
            if token in ("-nt", "--no-tools"):
                out["tools"] = "off"
            index += 1
            continue
        if token.startswith("-"):
            unknown.append(token)
        index += 1

    if unknown:
        out["modelled"] = False
    return out


def effective_command(session: dict) -> str:
    simple = (session.get("mode") or "simple") == "simple"
    if simple and (session.get("harness") or "pi") == "pi":
        return build_command(session)
    return (session.get("command") or "").strip()


def render_command(session: dict, message: str, expand_prompt: bool = True) -> list[str]:
    template = effective_command(session)
    if not template:
        raise RuntimeError("session command is empty")
    values = {
        "sessionId": session.get("sessionId") or "clutcha",
        "message": message,
        # Previews keep the placeholder: the control line is long, and its only
        # job here would be to bury the flags the user wants to inspect.
        "systemPrompt": system_prompt(session) if expand_prompt else "{systemPrompt}",
        "cwd": session.get("cwd") or cfg.BRIDGE_DIR,
    }

    argv: list[str] = []
    used_message = False
    for token in shlex.split(template):
        if "{" not in token:
            argv.append(token)
            continue
        expanded = token
        for key in PLACEHOLDERS:
            if "{" + key + "}" in expanded and key == "message":
                used_message = True
            expanded = expanded.replace("{" + key + "}", values[key])
        if expanded == "":
            # An empty value would leave a dangling flag ("--append-system-prompt").
            if argv and argv[-1].startswith("-"):
                argv.pop()
            continue
        argv.append(expanded)

    if not argv:
        raise RuntimeError("session command produced no arguments")
    if not used_message:
        raise RuntimeError("session command must contain {message}")
    return argv


def display_command(session: dict, message: str = "{message}") -> str:
    try:
        return shlex.join(render_command(session, message, expand_prompt=False))
    except Exception:
        return effective_command(session)


# --------------------------------------------------------------------------- #
# Working directory
# --------------------------------------------------------------------------- #

def working_dir(session: dict) -> str:
    raw = (session.get("cwd") or "").strip() or cfg.default_cwd()
    directory = os.path.abspath(os.path.expanduser(raw))
    if not os.path.isdir(directory):
        raise RuntimeError(
            f"working directory does not exist: {directory} — fix it on the Session tab"
        )
    return directory


CONTEXT_FILE_NAMES = ("AGENTS.md", "CLAUDE.md")


def check_cwd(value: str) -> dict:
    raw = (value or "").strip() or cfg.BRIDGE_DIR
    directory = os.path.abspath(os.path.expanduser(raw))
    result = {
        "ok": False,
        "input": value,
        "path": directory,
        "exists": os.path.isdir(directory),
        "writable": False,
        "contextFiles": [],
        "error": "",
    }
    if not os.path.exists(directory):
        result["error"] = "This path does not exist."
        return result
    if not os.path.isdir(directory):
        result["error"] = "This path is a file, not a folder."
        return result
    result["ok"] = True
    result["writable"] = os.access(directory, os.W_OK)
    try:
        result["contextFiles"] = [name for name in CONTEXT_FILE_NAMES if os.path.isfile(os.path.join(directory, name))]
    except Exception:
        pass
    return result


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #

def invoke(argv: list[str], session: dict, stdin_text: str | None = None) -> str:
    shown = shlex.join(argv[:8]) + (" …" if len(argv) > 8 else "")
    STATE.add("runtime", f"exec: {shown}")
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        input=stdin_text,
        timeout=int(session.get("timeoutSeconds") or 180),
        cwd=working_dir(session),
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise RuntimeError(f"exit {result.returncode}: {detail[-1] if detail else 'no stderr'}")
    return result.stdout.strip()


def reply(text: str) -> str:
    """One message in, one reply out. Never raises: the caller still replies."""
    session = cfg.session()
    started = time.time()
    try:
        argv = render_command(session, text)
        output = invoke(argv, session)
    except subprocess.TimeoutExpired:
        STATE.bump("errors")
        STATE.add("error", f"runtime timed out after {session.get('timeoutSeconds')}s", "error")
        return session.get("fallback") or ""
    except Exception as error:
        STATE.bump("errors")
        STATE.add("error", f"runtime failed: {error}", "error")
        return session.get("fallback") or ""

    elapsed = (time.time() - started) * 1000
    STATE.last_reply_ms = round(elapsed, 1)
    if not output:
        STATE.bump("errors")
        STATE.add("error", "runtime produced no output", "error", duration_ms=elapsed)
        return session.get("fallback") or ""
    STATE.add("agent", f"reply: “{output}”", duration_ms=elapsed)
    return output


# --------------------------------------------------------------------------- #
# Control directive
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# pi session files (reset / info)
# --------------------------------------------------------------------------- #

def pi_session_dir(session: dict) -> str:
    try:
        cwd = working_dir(session).rstrip("/")
    except Exception:
        cwd = os.path.abspath(os.path.expanduser(session.get("cwd") or cfg.BRIDGE_DIR)).rstrip("/")
    encoded = "--" + cwd.lstrip("/").replace("/", "-") + "--"
    return os.path.join(os.path.expanduser("~"), ".pi", "agent", "sessions", encoded)


def session_files(session: dict) -> list[str]:
    if (session.get("harness") or "pi") != "pi":
        return []
    session_id = session.get("sessionId") or ""
    if not session_id:
        return []
    pattern = os.path.join(pi_session_dir(session), f"*_{session_id}.jsonl")
    return sorted(glob.glob(pattern))


def session_info(session: dict) -> dict:
    files = session_files(session)
    if not files:
        return {"found": False, "path": None, "bytes": 0, "turns": 0, "updated": None}
    path = files[-1]
    turns = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if '"type":"message"' in line or '"type": "message"' in line:
                    turns += 1
    except Exception:
        pass
    try:
        stat = os.stat(path)
        updated = stat.st_mtime
        size = stat.st_size
    except Exception:
        updated, size = None, 0
    return {"found": True, "path": path, "bytes": size, "turns": turns, "updated": updated}


def archive_session(session: dict) -> dict:
    """Rename the session file instead of deleting it: history stays recoverable."""
    files = session_files(session)
    if not files:
        return {"ok": False, "error": "no session file found"}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = []
    for path in files:
        target = f"{path}.archived-{stamp}"
        try:
            os.rename(path, target)
            moved.append(target)
        except Exception as error:
            return {"ok": False, "error": str(error)}
    return {"ok": True, "archived": moved}
