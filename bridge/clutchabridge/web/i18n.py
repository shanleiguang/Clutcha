"""English and Chinese, one set of templates.

The pages are written in English in `pages.py`. This module swaps whole phrases
when the chosen language is Chinese: the table is keyed by the page's own English
text, so a phrase that gets reworded in the template simply stops being
translated — visible the moment the page is opened in Chinese — instead of
silently pointing at a key that no longer exists.

Matching tolerates the newlines and indentation that the HTML templates put
inside a sentence; the replacement is normalised to single spaces, which HTML
renders identically.

Not translated on purpose: log lines (`STATE.add`), which quote mail subjects,
paths and errors; the `pi` flag names; protocol labels such as `VM MESSAGE`.
"""

from __future__ import annotations

import re

from .. import config as cfg

# The toggle shows the language you would switch *to*.
LABELS = {"en": "中", "zh": "EN"}
TITLES = {"en": "中文", "zh": "English"}


def current() -> str:
    lang = (cfg.ui_cfg().get("lang") or "en").strip().lower()
    return lang if lang in LABELS else "en"


def is_chinese() -> bool:
    return current() == "zh"


def toggle_to() -> str:
    return "zh" if current() == "en" else "en"


def label() -> str:
    return LABELS[current()]


def title() -> str:
    return TITLES[current()]


# English source phrase -> Chinese. Longest first when applied, so "Session ID"
# wins over "Session".
ZH = {
    # -- chrome ------------------------------------------------------------
    "Status": "状态",
    "Setup": "设置",
    "Session": "会话",
    "Toggle theme": "切换主题",
    "never": "从未",
    "Time": "时间",
    "Type": "类型",
    "Detail": "详情",
    "Authorization code": "授权码",
    "Show token": "显示授权码",
    "local only (127.0.0.1)": "仅本机 (127.0.0.1)",

    # -- status: the diagram ------------------------------------------------
    "How it fits together": "整体结构",
    "this page is the middle box": "当前页面是中间这一格",
    "Clutcha App": "锦囊AI App",
    "the phone": "手机端",
    "encrypted letter": "加密信件",
    "mailbox": "邮箱",
    "sees only armor": "只能看到密文",
    "this program": "本程序",
    "pi session": "pi 会话",
    "the agent": "agent",
    "The answer comes back the same way, and both letters are sealed before they "
    "reach the mailbox. Nothing here listens on the network: an email account is the "
    "transport, which is why there is no port to open and no server to rent.":
        "回答沿同一条路返回，两封信在进入邮箱之前就已经封好。这里没有任何东西在网络上监听："
        "邮箱就是传输层，所以既不用开放端口，也不用租服务器。",

    # -- status: counters ---------------------------------------------------
    "Service": "服务",
    "Last check": "上次检查",
    "Messages": "消息",
    "Poll results": "轮询结果",
    "last 24h": "最近 24 小时",
    "In": "收",
    "Out": "发",
    "Replies": "回复",
    "Empty": "空轮",
    "Errors": "错误",
    "No data yet": "还没有数据",
    "Reply latency": "回复延迟",
    "Last reply": "上次回复",
    "Last message": "上次消息",
    "Activity": "活动",
    "Check now": "立即检查",
    "Nothing yet.": "暂无记录。",
    "Waiting for setup": "等待设置",
    "This bridge has not sent or received anything yet.": "这个 bridge 还没有收发过任何东西。",
    "Running": "运行中",
    "every": "每",
    "next in": "下次",
    "no new messages": "没有新消息",
    "no session file yet": "还没有会话文件",
    "checks total": "次检查",
    "error(s)": "个错误",
    "started": "启动",
    "never checked": "还没查过",
    "ago": "前",
    "yet": "过",
    "fill in your mailbox, save — then scan the pairing code with the Clutcha app.":
        "填好邮箱并保存，然后用锦囊AI App 扫配对码。",

    # -- setup: mailbox -----------------------------------------------------
    "Setup needed": "需要设置",
    "Auto (system)": "跟随系统",
    "Fill in your mailbox below and save.": "在下面填好邮箱并保存。",
    "Use an app-specific token, not your account password.": "用应用专用密码，不要用账号密码。",
    "Communication mailbox": "通信邮箱",
    "the address the app writes to and reads from": "app 收发信件用的地址",
    "Name": "名称",
    "— this Mac's name": "— 这台电脑的名字",
    "Letters are signed with it, and the phone shows it as the machine that answered.":
        "信件用它签名，手机端会把它显示成回答你的那台机器。",
    "The app itself is called Clutcha, so repeating that here only blurs which end is which.":
        "app 本身已经叫锦囊AI，这里再写一遍只会让两端分不清。",
    "Changing it reaches the phone the next time you pair.": "改名后要重新配对才会传到手机上。",
    "Email address": "邮箱地址",
    "Inbox": "收件",
    "POP3 or IMAP": "POP3 或 IMAP",
    "Protocol": "协议",
    "Host": "服务器",
    "Port": "端口",

    "Outgoing mail": "发件",
    "Save": "保存",
    "Test connection": "测试连接",
    "The login name is the address above.": "登录名就是上面的邮箱地址。",
    "with 0600 permissions — which is exactly why this page must stay on 127.0.0.1.":
        "权限 0600 —— 这正是这个页面只能留在 127.0.0.1 的原因。",
    "One mailbox for both sides: the app writes to it, the bridge answers in it.":
        "两端共用一个邮箱：app 往里写，bridge 在里面回。",

    # -- setup: polling -----------------------------------------------------
    "Polling": "轮询周期",
    "Poll interval": "轮询周期",
    "Automatic cleanup": "自动清理",
    "delete yesterday's letters once a day": "每天删除昨天的信件",
    "Cleanup": "清理",
    "Run once a day": "每天运行一次",
    "At": "时间",
    "View log": "查看日志",
    "how often the mailbox is checked": "多久查一次邮箱",
    "Interval (seconds, 60–3600)": "间隔（秒，60–3600）",
    "Examine at most (new messages per check)": "每次最多检查（新邮件数）",
    "Polling enabled": "启用轮询",
    "Mail delivery is not instant — a message often takes about a minute to appear in the inbox.":
        "邮件不是即时到达的 —— 一封信常常要一分钟才出现在收件箱里。",
    "The app fetches on demand, so this interval only decides how quickly the bridge notices something new.":
        "app 是按需取信的，所以这个间隔只决定 bridge 多快发现有新东西。",
    "A dedicated agent mailbox": "独立的 agent 邮箱",
    "planned": "计划中",
    "A separate mailbox for the agent will be an option later; switching modes will require re-pairing the app.":
        "以后会提供单独给 agent 用的邮箱；切换模式需要重新配对 app。",

    # -- setup: letter ------------------------------------------------------
    "Letter template": "信件模版",
    "the wrapper around the ciphertext": "包在密文外面的那层",
    "Language": "语言",
    "Vary the wording": "变换措辞",
    "Pick a random greeting and closing each time": "每次随机挑一个问候语和落款",
    "Greeting variants · one per line, picked at random": "问候语候选 · 一行一条，随机取用",
    "Subject · 中文": "主题 · 中文",
    "Subject · English": "主题 · English",
    "Closing variants · one per line, blank allowed": "落款候选 · 一行一条，可以留空",
    "Letter body · must contain": "信件正文 · 必须包含",
    "Save letter": "保存",
    "Preview": "预览",
    "Send a test letter to myself": "给自己发一封测试信",
    "Delivery is not instant, and a test letter is a real message: it costs one round trip and counts "
    "against your provider's reputation.":
        "邮件不是即时的，而且测试信是真实邮件：占一次往返，也算进邮箱服务商的信誉。",
    "Use it when you change the letter, not in a loop.": "改信件时用一次，不要循环发。",
    "As it will arrive": "信件预览",
    "this is what lands in the inbox": "这就是收件箱里看到的",
    "Subject": "主题",

    # -- setup: pairing -----------------------------------------------------
    "Pairing": "配对",
    "scan once in the Clutcha app · Remote tab": "在锦囊AI App 的 Remote 标签扫一次",
    "Agent": "Agent",
    "Address": "地址",
    "Tools": "工具",
    "Copy pairing code": "复制配对码",
    "Show pairing code": "查看配对码",
    "The code contains both key pairs and the transport settings.": "这串码包含双方密钥和传输设置。",
    "Treat it like a password: anyone who scans it can talk to this bridge, and if tools are enabled on the Session tab, can run commands on this Mac.":
        "把它当密码看待：谁扫到都能和这个 bridge 对话，如果会话页开了工具，还能在这台电脑上执行命令。",
    "The QR code could not be rendered — reload the page.": "二维码没能画出来 —— 刷新页面。",
    "If it stays empty the": "如果仍然是空的，说明",
    "package is missing: run install.command again.": "包没装上：重新运行 install.command。",

    # -- session ------------------------------------------------------------
    "the bridge's own conversation": "bridge 自己的对话",
    "Session ID": "会话 ID",
    "pi creates it on the first message.": "pi 会在收到第一条消息时创建它。",
    "Do not point this at a conversation you have open in the terminal — a session id is a name, and reusing one merges two conversations.":
        "不要指向你在终端里开着的对话 —— 会话 ID 只是一个名字，复用同一个会把两段对话合并。",
    "Changing the id or the folder starts a different one.": "改 ID 或改目录，就等于开始另一段对话。",
    "Passed as": "以",
    ", exactly as typed.": "原样传入。",
    "Local or remote is pi's business, not the bridge's.": "本地还是云端是 pi 的事，不是 bridge 的。",
    "empty — runs in the bridge folder:": "留空 —— 在 bridge 目录里运行：",
    "(as pi is configured)": "（按 pi 的配置）",
    "pi's default": "pi 的默认模型",
    "— the bridge's own": "— bridge 自己的",
    "Model": "模型",
    "pi's default": "pi 的默认模型",
    "Working directory": "工作目录",
    "Check": "检查",
    "Thinking": "思考",
    "Timeout (seconds)": "超时（秒）",
    "Reply limit (characters)": "回复上限（字符）",
    "How long a reply may take before the bridge gives up and sends the fallback.":
        "一次回复最多等多久，超时就发送兜底回复。",
    "Longer answers are cut here; the full text stays on the Mac.":
        "更长的回答会在这里被截断，全文留在这台电脑上。",
    "Fallback reply": "兜底回复",
    "— sent when the agent fails or times out": "— agent 失败或超时时发送",
    "(empty: say nothing)": "（留空：什么都不说）",
    "Advanced": "高级",
    "Let the agent use tools": "允许 agent 使用工具",
    "Off adds": "关闭会加",
    "the agent can only answer with text.": "agent 只能用文字回答。",
    "On adds nothing, so whatever your pi configuration allows becomes reachable from a paired phone —":
        "打开则什么都不加，于是 pi 配置里允许的一切都能被已配对的手机触达 ——",
    "There is no approval step and no login: the mailbox is the only door.":
        "没有审批环节也没有登录：邮箱就是唯一的那扇门。",
    "System prompt": "系统提示",
    "— optional, appended to pi's own": "— 可选，追加在 pi 自己的提示之后",
    "Optional persona…": "可选的人设…",
    "Command source": "命令来源",
    "Built from these fields": "由上面这些字段拼出来",
    "Hand-written command": "手写的命令",
    "Command line": "命令行",
    "— placeholders:": "— 占位符：",
    "Runs as argv, no shell.": "以 argv 方式运行，不经 shell。",
    "Switching back to \"built from these fields\" discards whatever you wrote here.":
        "切回“由上面这些字段拼出来”会丢弃这里写的内容。",
    "Test session": "测试会话",
    "Long answers": "长回复",
    "Limit": "上限",
    "What happens": "会发生什么",
    "If it fails": "失败时",
    "Timeout": "超时",
    "including": "包括",
    "File": "文件",
    "Size": "大小",
    "Turns": "轮次",
    "Updated": "更新于",
    "Archive session": "归档会话",
    "Preview command": "预览命令",
    "not created yet": "还没有生成",
    "Archiving renames the session file (it stays on disk), so the next message starts a fresh conversation.":
        "归档只是给会话文件改名（仍然留在磁盘上），下一条消息就会开始一段新对话。",
    "characters. The ciphertext is base64 (+33%) and the mail provider has a size limit, so a huge answer would not arrive at all.":
        "字符。密文还要 base64 编码（+33%），而邮箱服务商有大小限制，太大的回答根本寄不到。",
    "The reply is cut, a marker is appended, and the complete text is written to":
        "回复会被截断并加上标记，完整文本写到",
    "on this computer.": "（在这台电脑上）。",
    "seconds. Tool-heavy turns take longer than chat; if replies stop arriving, raise this first.":
        "秒。带工具的一轮比聊天慢得多；如果回复开始收不到，先调大这个值。",
    "The fallback reply is sent instead of nothing, so the phone never just goes quiet. The reason lands in the Status tab.":
        "会发送兜底回复而不是什么都不发，手机端不会莫名其妙地安静；原因记在状态页。",
    "why replies get cut": "为什么回复会被截断",
    "Session state": "会话状态",
    "pi session file": "pi 会话文件",
    "managed by the command": "由命令管理",
    "Archive session": "归档会话",
    "missing folder": "目录不存在",
}

_PATTERNS = [
    (
        re.compile(
            r"(?<![A-Za-z])" + r"\s+".join(re.escape(word) for word in phrase.split()) + r"(?![A-Za-z])",
        ),
        replacement,
    )
    for phrase, replacement in sorted(ZH.items(), key=lambda item: -len(item[0]))
]


# `<script>` and `<style>` are not prose. Translating them is how `Content-Type`
# became `Content-类型` and fetch stopped working: a one-word entry like "Type"
# matched a header name. They are cut out before matching and put back after.
_OPAQUE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)


def apply(html: str) -> str:
    """Translate a whole rendered page. No-op in English."""
    if not is_chinese():
        return html
    parts: list[str] = []
    cursor = 0
    for match in _OPAQUE.finditer(html):
        parts.append(text(html[cursor:match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(text(html[cursor:]))
    return "".join(parts)


def text(value: str) -> str:
    """Translate one phrase (used where a template builds a label by hand)."""
    if not is_chinese():
        return value
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(lambda _match, replacement=replacement: replacement, value)
    return value


