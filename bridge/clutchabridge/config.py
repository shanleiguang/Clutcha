"""Configuration: load, migrate (v1 -> v2 -> v3), save.

    me      the human + the app (mailbox, app identity)
    monkey  the agent + the bridge's session
    mail    the letter that carries the ciphertext (language, wording)
    poll    polling policy
    server  where the web UI listens

`me.mail` is used by both sides while `monkey.mail.mode == "shared"` (one
mailbox, self-send).
"""

from __future__ import annotations

import copy
import json
import socket
import os
import shutil
import time

BRIDGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = (
    os.environ.get("CLUTCHA_BRIDGE_CONFIG")
    or os.environ.get("VMESSAGER_BRIDGE_CONFIG")
    or os.path.join(BRIDGE_DIR, "config.json")
)
# Runtime files sit next to the config, so a config pointed elsewhere (tests,
# a second instance) does not scribble into the checkout.
STATE_DIR = os.path.dirname(os.path.abspath(CONFIG_PATH)) or BRIDGE_DIR

# Only {sessionId}, {message}, {systemPrompt} and {cwd} are substituted.
# Everything else (model, thinking, tools) belongs to pi's own configuration,
# so whatever the user writes here is exactly what runs.
def default_cwd() -> str:
    """Where the agent runs by default: its own folder, not this source tree.

    pi writes session files and touches files next to itself; pointing it at the
    bridge's own directory means a stray command edits the program that is
    running. The folder is created when the bridge starts.
    """
    return os.path.join(os.path.expanduser("~"), ".clutcha-bridge")


def default_agent_name() -> str:
    """The Mac's own name.

    Letters are signed with this, and the phone shows it as where the answers
    come from, so it should say which machine replied — not repeat the product's
    name, which is what the app already calls itself.
    """
    try:
        name = socket.gethostname().split(".")[0].strip()
    except Exception:
        name = ""
    return name or "Clutcha"


DEFAULT_PI_COMMAND = (
    "pi -p --session-id {sessionId} -nt "
    "--append-system-prompt {systemPrompt} {message}"
)

# Shown when the agent fails or times out. Silence is the worst outcome: the
# phone would look like the message was simply lost.
DEFAULT_FALLBACK = "(No answer — the agent did not finish in time. Check the bridge's Status tab.)"

# Polling bounds live here because they are part of the configuration's
# contract: anything below 60s is indistinguishable from hammering a mailbox
# (and POP3 allows one session at a time, so it also fights the phone).
POLL_MIN = 60
POLL_MAX = 3600
DEFAULT_POLL_SECONDS = 180

CONFIG: dict = {}


def blank_config() -> dict:
    return {
        "version": 4,
        "server": {"host": "127.0.0.1", "port": 8787},
        "me": {
            "name": "Me",
            "mail": {
                "address": "",
                "inbox": {
                    "protocol": "pop3",
                    "host": "",
                    "port": 995,
                    "useSSL": True,
                    "starttls": False,
                    "username": "",
                    "token": "",
                },
                "smtp": {
                    "host": "",
                    "port": 465,
                    "useSSL": True,
                    "starttls": False,
                    "username": "",
                    "token": "",
                },
            },
            "identity": {"privateKey": "", "publicKey": ""},
        },
        "monkey": {
            # The Mac's name: letters are signed with it, and the phone shows
            # it as the machine behind the answers.
            "name": default_agent_name(),
            "identity": {"privateKey": "", "publicKey": ""},
            "mail": {"mode": "shared", "own": {}},
            "session": {
                "harness": "pi",
                # "simple" = the form owns the command; "raw" = the command string
                # is hand-written and the form only displays it.
                "mode": "simple",
                "sessionId": "clutcha-main",
                "cwd": default_cwd(),
                # Passed straight through as --model. The bridge does not know
                # or care whether the model is local or in the cloud; pi is
                # configured ahead of time and empty means "pi's default".
                "model": "",
                # Two choices on the Session page: "off", or nothing at all so
                # pi's own configuration decides. Off by default — a bridge that
                # silently spends tokens on reasoning is a surprise, not a feature.
                "thinking": "off",
                # "off" adds -nt. "on" adds nothing: whatever the user's own pi
                # configuration allows is then reachable from a paired phone.
                # On by default — the bridge is for an agent that can work.
                "tools": "on",
                "systemPrompt": "",
                "timeoutSeconds": 300,
                "fallback": DEFAULT_FALLBACK,
                # Above this, the bridge cuts the answer and says so. Mail size
                # and the armor expansion (+33%) make huge replies undeliverable.
                "replyMaxChars": 6000,
                "command": "",
            },
        },
        "mail": {
            "lang": "auto",  # auto | zh | en
            "vary": True,
            "subject": {"zh": "Clutcha 消息", "en": "Clutcha message"},
            "greeting": {
                "zh": ["你好，", "嗨，", "在吗，", "打扰一下，", "见字如面，"],
                "en": ["Hi,", "Hello,", "Hey,", "Quick note —"],
            },
            "body": {
                "zh": "这是一条通过 Clutcha 发送的消息，请在 App 中查看。\n发送时间：{time}\n\n{armored}",
                "en": "A message sent through Clutcha. Open the app to read it.\nSent: {time}\n\n{armored}",
            },
            "closing": {
                "zh": ["辛苦了。", "回头聊。", "方便时看看。", "谢谢。", ""],
                "en": ["Thanks.", "Talk soon.", "No rush.", ""],
            },
        },
        # Off by default: deleting mail is not something to discover later.
        "cleanup": {"enabled": False, "hour": 3},
        "poll": {"enabled": True, "intervalSeconds": DEFAULT_POLL_SECONDS,
                 "maxPerCycle": 5, "maxScan": 20},
        "ui": {"theme": "auto", "lang": "en"},
    }


def _deep_fill(defaults: dict, actual: dict) -> dict:
    """defaults <- actual, recursively, keeping unknown keys."""
    out = copy.deepcopy(actual) if actual else {}
    for key, value in defaults.items():
        if key not in out or out[key] in (None, ""):
            out[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(out[key], dict):
            out[key] = _deep_fill(value, out[key])
    return out


def _mail_block(source: dict, default_port: int, default_ssl: bool) -> dict:
    source = source or {}
    return {
        "protocol": source.get("protocol", "pop3"),
        "host": source.get("host", ""),
        "port": int(source.get("port") or default_port),
        "useSSL": bool(source.get("useSSL", default_ssl)),
        "starttls": bool(source.get("starttls", False)),
        "username": source.get("username", ""),
        "token": source.get("password") or source.get("token") or "",
    }


def _migrate_subject(raw: dict) -> dict:
    """v2 had one global `subject`; v3 keeps one per language."""
    template = copy.deepcopy(blank_config()["mail"])
    legacy = str(raw.get("subject") or "").strip()
    if legacy and legacy not in ("vMessager message", "Clutcha message"):
        template["subject"] = {"zh": legacy, "en": legacy}
    return template


def _normalise_poll(config: dict) -> dict:
    """Keep the stored interval inside the bounds, and move the old 60s default
    to the new one. 60 is now the floor, so a stored 60 is far more likely to be
    the previous default than a deliberate choice."""
    poll = config.setdefault("poll", {})
    try:
        value = int(poll.get("intervalSeconds") or DEFAULT_POLL_SECONDS)
    except Exception:
        value = DEFAULT_POLL_SECONDS
    if value == 60:
        value = DEFAULT_POLL_SECONDS
    poll["intervalSeconds"] = max(POLL_MIN, min(POLL_MAX, value))
    return config


def _migrate_v3(raw: dict) -> dict:
    config = _deep_fill(blank_config(), raw)
    config["version"] = 4
    return _normalise_poll(config)


def _migrate_v2(raw: dict) -> dict:
    config = _deep_fill(blank_config(), raw)
    # "Monkey" was the old default name, not a user choice — the app shows it.
    if config["monkey"].get("name") == "Monkey":
        config["monkey"]["name"] = "Home"
    config["mail"] = _migrate_subject(raw)
    # The command string stays exactly as it was: we only derive the form's
    # display values from it. Rewriting it here could silently drop flags the
    # user added by hand, so "raw" mode is the safe default whenever the
    # command contains anything the simple form does not model.
    from . import agent  # local import: agent imports config

    session = config["monkey"]["session"]
    parsed = agent.parse_command(session.get("command") or "")
    session.update({key: parsed[key] for key in ("tools", "thinking", "model") if key in parsed})
    session["mode"] = "simple" if parsed.get("modelled", False) else "raw"
    config.pop("subject", None)
    return config


def migrate(raw: dict) -> tuple[dict, bool]:
    """Return (config, changed). Old files are rewritten after a backup."""
    if not raw:
        return blank_config(), False

    version = int(raw.get("version") or 0)
    if version >= 4:
        config = _deep_fill(blank_config(), raw)
        return config, config != raw
    if version == 3:
        return _migrate_v3(raw), True
    if version == 2:
        return _migrate_v3(_migrate_v2(raw)), True

    # ---------------------------------------------------------------- v1 ---
    config = blank_config()
    inbox = raw.get("inbox") or {}
    smtp = raw.get("smtp") or {}
    keys = raw.get("keys") or {}
    runtime = raw.get("runtime") or raw.get("brain") or {}
    provision = raw.get("appProvision") or {}

    config["server"] = dict(raw.get("monitor") or config["server"])
    config["mail"] = _migrate_subject(raw)

    address = raw.get("peerEmail") or inbox.get("username") or provision.get("email") or ""
    config["me"]["name"] = provision.get("identityName") or "Me"
    config["me"]["mail"]["address"] = address
    config["me"]["mail"]["inbox"] = _mail_block(inbox, 995, True)
    config["me"]["mail"]["smtp"] = _mail_block(smtp, 465, True)
    config["me"]["identity"] = {
        "privateKey": keys.get("appPrivate", ""),
        "publicKey": keys.get("peerPublic", ""),
    }

    config["monkey"]["name"] = raw.get("agentName") or "Monkey"
    config["monkey"]["identity"] = {
        "privateKey": keys.get("assistantPrivate", ""),
        "publicKey": keys.get("assistantPublic", ""),
    }

    session = config["monkey"]["session"]
    kind = runtime.get("kind", "pi")
    session["harness"] = "pi" if kind == "pi" else "command"
    if kind == "pi":
        parts = ["pi", "-p", "--session-id", "{sessionId}"]
        if runtime.get("tools"):
            parts += ["--tools", str(runtime.get("toolList") or "bash,read,write,edit")]
        else:
            parts.append("-nt")
        if runtime.get("noContextFiles"):
            parts.append("-nc")
        if runtime.get("thinking"):
            parts += ["--thinking", str(runtime["thinking"])]
        if runtime.get("model"):
            parts += ["--model", str(runtime["model"])]
        parts += ["--append-system-prompt", "{systemPrompt}", "{message}"]
        session["command"] = " ".join(parts)
        session["mode"] = "simple"
    else:
        command = list(runtime.get("command") or [])
        command += list(runtime.get("argsTemplate") or [])
        session["command"] = " ".join(command) or DEFAULT_PI_COMMAND
        session["mode"] = "raw"

    from . import agent

    parsed = agent.parse_command(session["command"])
    for key in ("tools", "thinking", "model"):
        if key in parsed:
            session[key] = parsed[key]

    session["sessionId"] = runtime.get("sessionId") or session["sessionId"]
    session["cwd"] = runtime.get("cwd") or session["cwd"]
    session["systemPrompt"] = runtime.get("persona") or ""
    session["timeoutSeconds"] = int(runtime.get("timeoutSeconds") or 180)
    session["fallback"] = runtime.get("fallback") or ""

    config["poll"]["intervalSeconds"] = int(raw.get("pollIntervalSeconds") or DEFAULT_POLL_SECONDS)
    config["poll"]["maxScan"] = int(raw.get("maxScan") or 20)
    return _normalise_poll(config), True


def load_config() -> dict:
    """Load config.json, migrating older files (with a backup) when needed."""
    global CONFIG
    raw: dict = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        raw = {}

    config, changed = migrate(raw)
    CONFIG = config
    if changed:
        if raw:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = f"{CONFIG_PATH}.v{int(raw.get('version') or 1)}.bak-{stamp}"
            try:
                shutil.copy2(CONFIG_PATH, backup)
            except Exception:
                pass
        save_config()
    return CONFIG


def save_config() -> None:
    """Write 0600: the file holds mail tokens and private keys."""
    directory = os.path.dirname(CONFIG_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(CONFIG, handle, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG_PATH)


# --------------------------------------------------------------------------- #
# Readers
# --------------------------------------------------------------------------- #

def me() -> dict:
    return CONFIG.get("me") or {}


def me_mail() -> dict:
    return me().get("mail") or {}


def monkey() -> dict:
    return CONFIG.get("monkey") or {}


def session() -> dict:
    return monkey().get("session") or {}


def mail_template() -> dict:
    return CONFIG.get("mail") or {}


def poll_cfg() -> dict:
    return CONFIG.get("poll") or {}


def cleanup_cfg() -> dict:
    return CONFIG.setdefault("cleanup", {})


def ui_cfg() -> dict:
    """Look, not identity: the web page's language and theme."""
    ui = CONFIG.setdefault("ui", {})
    return ui


def address() -> str:
    """Where the app sends: the shared mailbox, or the monkey's own one."""
    mail = monkey().get("mail") or {}
    if mail.get("mode") == "own":
        own = mail.get("own") or {}
        if own.get("address"):
            return own["address"]
    return me_mail().get("address") or ""


def mailbox() -> dict:
    """Credentials the bridge reads with (and replies from)."""
    mail = monkey().get("mail") or {}
    if mail.get("mode") == "own":
        own = mail.get("own") or {}
        if own.get("inbox"):
            return {"inbox": own["inbox"], "smtp": own.get("smtp") or own["inbox"]}
    return {"inbox": me_mail().get("inbox") or {}, "smtp": me_mail().get("smtp") or {}}


def keys() -> dict:
    """Both key pairs: the monkey's and the app's (provisioned)."""
    mer = monkey().get("identity") or {}
    peer = me().get("identity") or {}
    return {
        "assistantPrivate": mer.get("privateKey") or "",
        "assistantPublic": mer.get("publicKey") or "",
        "peerPublic": peer.get("publicKey") or "",
        "appPrivate": peer.get("privateKey") or "",
    }


def is_configured() -> bool:
    creds = mailbox()
    inbox = creds["inbox"]
    smtp = creds["smtp"]
    pair = keys()
    return bool(
        pair["assistantPrivate"]
        and pair["assistantPublic"]
        and pair["peerPublic"]
        and inbox.get("host")
        and inbox.get("username")
        and inbox.get("token")
        and smtp.get("host")
        and address()
    )


load_config()
