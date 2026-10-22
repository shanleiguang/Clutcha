"""Bridge commands — control mail, answered by the bridge instead of the model.

A letter whose plaintext begins with ``#clutcha:`` is a management request. It
never reaches the agent: the reply is built here, which is why a ping comes back
in seconds instead of after a model turn.

Two verbs::

    #clutcha:ping
    #clutcha:config {"poll": {"intervalSeconds": 300}, "agent": {"model": "..."}}

The JSON deliberately matches ``config.json``, so what the app sends is what you
would otherwise edit by hand.

What is deliberately **not** settable by mail: ``agent.tools``, ``agent.cwd``,
``agent.sessionId``, the raw command, and anything under ``mail`` or ``ui``.
Tools decide what the model may do on this Mac; that stays behind the Session
page, where a person is looking at the machine. A letter can be written by
anyone holding the key, and the key can be on a phone that is not yours.

The reply is Markdown, because that is what the app renders.
"""

from __future__ import annotations

import json
import time

from . import agent
from . import config as cfg
from . import __version__
from .state import STATE

PREFIX = "#clutcha:"

# Anything here is refused by name, so the refusal can say why.
FORBIDDEN = {
    "agent.tools": "tools are decided on the Mac, on the Session page",
    "agent.cwd": "the working directory is a filesystem path, not a mail setting",
    "agent.sessionId": "the session id names a conversation on the Mac",
    "agent.command": "the raw command line stays on the Mac",
    "agent.systemPrompt": "the system prompt is edited on the Mac",
    "mail": "mailbox credentials are edited on the Mac",
    "ui": "this bridge has no screen to theme",
}


def is_command(text: str) -> bool:
    return (text or "").lstrip().lower().startswith(PREFIX)


def split(text: str) -> tuple[str, str]:
    """`#clutcha:verb {json}` -> ("verb", "{json}")."""
    body = (text or "").lstrip()[len(PREFIX):].strip()
    verb, _, rest = body.partition("\n")
    verb = verb.strip()
    head, _, rest_of_line = verb.partition(" ")
    payload = (rest_of_line + "\n" + rest).strip() if rest_of_line else rest.strip()
    return head.lower(), payload


def handle(text: str) -> str | None:
    """Answer a control mail. None when this is ordinary conversation."""
    if not is_command(text):
        return None
    verb, payload = split(text)
    if verb in ("ping", "status"):
        return _ping()
    if verb in ("config", "update", "set"):
        return _config(payload)
    if verb in ("new", "reset"):
        return _new()
    if verb == "help":
        return _help()
    return _help(f"未知命令：{verb}")


# -- ping ------------------------------------------------------------------- #


def _duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 90:
        return f"{seconds} 秒"
    if seconds < 5400:
        return f"{round(seconds / 60)} 分钟"
    hours, rest = divmod(seconds, 3600)
    return f"{hours} 小时 {rest // 60} 分" if rest // 60 else f"{hours} 小时"


def _ago(stamp: float | None) -> str:
    if not stamp:
        return "尚未检查"
    return f"{_duration(time.time() - stamp)}前"


def _onoff(value) -> str:
    return "on" if value not in (False, "off", "0", 0, None, "") else "off"


def _ping() -> str:
    snap = STATE.snapshot()
    session = cfg.session()
    poll = cfg.poll_cfg()
    model = session.get("model") or "pi 的默认模型"
    try:
        folder = agent.working_dir(session)
    except Exception:
        folder = session.get("cwd") or "—"

    interval = poll.get("intervalSeconds")
    polled = "已开启" if _onoff(poll.get("enabled")) == "on" else "已暂停"
    lines = [
        f"**Clutcha Bridge 正常在线**",
        "",
        f"当前模型：`{model}`",
        f"工作目录：`{folder}`",
        f"轮询周期：{interval} 秒（{polled}）",
        "",
        f"会话：`{session.get('sessionId')}` · 超时 {session.get('timeoutSeconds')} 秒"
        f" · 工具{_cn_onoff(session.get('tools'))}",
        f"运行时长：{_duration(snap['uptime'])} · 累计 {snap['polls']} 次检查，"
        f"{snap['received']} 收 / {snap['replied']} 回 / {snap['errors']} 异常",
        f"上次检查：{snap.get('lastPollResult') or '—'}（{_ago(snap.get('lastPollAt'))}）",
    ]
    return "\n".join(lines)


def _cn_onoff(value) -> str:
    return "开启" if _onoff(value) == "on" else "关闭"


# -- config ----------------------------------------------------------------- #


def _bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _num(value, low: int, high: int) -> int:
    return max(low, min(high, int(float(value))))


def _config(payload: str) -> str:
    if not payload:
        return _settings() + "\n\nSend `#clutcha:config {\"poll\": {\"intervalSeconds\": 300}}` to change one."
    try:
        wanted = json.loads(payload)
    except Exception as error:
        return f"**Clutcha Bridge** · 未生效\n\nJSON 解析失败：`{error}`\n\n一项设置都没有改动。"
    if not isinstance(wanted, dict):
        return "**Clutcha Bridge** · 未生效\n\n需要一个对象，例如 `{\"poll\": {\"intervalSeconds\": 300}}`。"

    applied: list[str] = []
    refused: list[str] = []
    poll = cfg.poll_cfg()
    session = cfg.session()

    for block, values in wanted.items():
        if block in FORBIDDEN:
            refused.append(f"{block} — {FORBIDDEN[block]}")
            continue
        if not isinstance(values, dict):
            refused.append(f"{block} — expected an object of settings")
            continue
        for key, value in values.items():
            path = f"{block}.{key}"
            if path in FORBIDDEN:
                refused.append(f"{path} — {FORBIDDEN[path]}")
                continue
            if block == "poll":
                note = _apply_poll(poll, key, value)
            elif block == "agent":
                note = _apply_agent(session, key, value)
            else:
                note = f"{path} — not a bridge setting"
            (applied if note and " — " not in note else refused).append(note)

    if applied:
        cfg.save_config()
        # The loop sleeps until next_poll_at; without a nudge a new interval
        # would only take effect after the old one expired.
        STATE.wake.set()
        STATE.add("service", "settings changed by mail: " + ", ".join(applied))

    lines = [f"**Clutcha Bridge** · {'配置已更新' if applied else '没有改动'}", ""]
    lines += [f"✓ {item}" for item in applied]
    lines += [f"✗ {item}" for item in refused]
    if applied:
        lines += ["", _settings_block()]
    return "\n".join(lines)


def _apply_poll(poll: dict, key: str, value) -> str:
    if key == "enabled":
        poll["enabled"] = _bool(value)
        return f"poll.enabled = {_cn_onoff(poll['enabled'])}"
    if key == "intervalSeconds":
        from .service import clamp_interval

        poll["intervalSeconds"] = clamp_interval(_num(value, 1, 86400))
        return f"poll.intervalSeconds = {poll['intervalSeconds']} 秒"
    if key == "maxScan":
        poll["maxScan"] = _num(value, 1, 200)
        return f"poll.maxScan = {poll['maxScan']} 封"
    if key == "maxPerCycle":
        poll["maxPerCycle"] = _num(value, 1, 20)
        return f"poll.maxPerCycle = {poll['maxPerCycle']} 封"
    return f"poll.{key} — not a setting"


def _new() -> str:
    """Start a fresh pi session. The old file is renamed, not deleted: a session
    you ended by accident should still be readable on the Mac."""
    session = cfg.session()
    result = agent.archive_session(session)
    if result.get("ok"):
        moved = len(result.get("archived") or [])
        STATE.add("service", f"session archived by mail ({moved} file(s))")
        return "\n".join(
            [
                "**Clutcha Bridge** · 新会话已开始",
                "",
                f"旧会话已归档（{moved} 个文件）。下一条消息会新建一个 pi 会话。",
                f"会话 ID：`{session.get('sessionId')}`",
            ]
        )
    reason = result.get("error") or "未知原因"
    return "\n".join(
        [
            "**Clutcha Bridge** · 新会话已就绪",
            "",
            f"旧会话没有归档（{reason}），但下一条消息仍会开始新的一轮上下文。",
            f"会话 ID：`{session.get('sessionId')}`",
        ]
    )


def _apply_agent(session: dict, key: str, value) -> str:
    if key == "model":
        session["model"] = str(value or "").strip()
        return f"agent.model = {session['model'] or 'pi 默认模型'}"
    if key == "timeoutSeconds":
        session["timeoutSeconds"] = _num(value, 30, 3600)
        return f"agent.timeoutSeconds = {session['timeoutSeconds']} 秒"
    if key == "thinking":
        session["thinking"] = str(value or "").strip()
        return f"agent.thinking = {session['thinking'] or '默认'}"
    if key == "replyMaxChars":
        session["replyMaxChars"] = _num(value, 500, 20000)
        return f"agent.replyMaxChars = {session['replyMaxChars']} 字符"
    return f"agent.{key} — not a setting"


def _settings_block() -> str:
    session = cfg.session()
    poll = cfg.poll_cfg()
    return "\n".join(
        [
            f"轮询：{_cn_onoff(poll.get('enabled'))} · 每 {poll.get('intervalSeconds')} 秒"
            f" · 每次扫 {poll.get('maxScan')} 封 · 每轮最多回 {poll.get('maxPerCycle')} 封",
            f"模型：`{session.get('model') or 'pi 默认模型'}`"
            f" · 超时 {session.get('timeoutSeconds')} 秒 · 思考 {session.get('thinking') or '默认'}",
            f"回复上限：{session.get('replyMaxChars')} 字符 · 工具{_cn_onoff(session.get('tools'))}",
        ]
    )


def _settings() -> str:
    return f"**Clutcha Bridge** · 当前配置\n\n{_settings_block()}"


def _help(prefix: str = "") -> str:
    lines = ["**Clutcha Bridge** · 命令"]
    if prefix:
        lines += ["", prefix]
    lines += [
        "",
        "`#clutcha:ping` — 在线状态、模型、工作目录、轮询周期",
        "`#clutcha:new` — 归档当前会话，下一条消息开始新会话",
        "`#clutcha:config {json}` — 改运行参数，返回改了哪些",
        "",
        "可改：`poll.enabled`、`poll.intervalSeconds`（60–3600）、`poll.maxScan`、",
        "`poll.maxPerCycle`、`agent.model`、`agent.timeoutSeconds`、`agent.thinking`、",
        "`agent.replyMaxChars`。",
        "",
        "邮件改不了：工具开关、工作目录、会话 ID、信箱、原始命令。",
        "",
        "不带 `#clutcha:` 前缀的内容，都是发给模型的消息，不是命令。",
    ]
    return "\n".join(lines)
