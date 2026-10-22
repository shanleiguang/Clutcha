"""The three tabs: Status, Setup, Session. All English, all server-rendered."""

from __future__ import annotations

import os
import time
from datetime import datetime
from html import escape

from .. import APP_NAME
from .. import __version__
from .. import agent
from .. import config as cfg
from .. import service
from .. import template as letter_template
from ..state import STATE
from . import assets, charts, i18n

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} 天 {hours} 小时" if i18n.is_chinese() else f"{days}d {hours}h"
    if hours:
        return f"{hours} 小时 {minutes} 分" if i18n.is_chinese() else f"{hours}h {minutes}m"
    return f"{minutes} 分钟" if i18n.is_chinese() else f"{minutes}m"


def _ago(timestamp: float | None) -> str:
    if not timestamp:
        return "never"
    delta = max(0, time.time() - timestamp)
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    return f"{int(delta // 3600)}h ago"


def _status_line() -> tuple[str, str]:
    if not cfg.is_configured():
        return "warn", "Not configured — open the Setup tab"
    if STATE.polling:
        return "busy", "Checking the mailbox…"
    interval = int(cfg.poll_cfg().get("intervalSeconds") or cfg.DEFAULT_POLL_SECONDS)
    if not cfg.poll_cfg().get("enabled", True):
        return "warn", "Polling paused"
    countdown = ""
    if STATE.next_poll_at:
        left = max(0, int(STATE.next_poll_at - time.time()))
        countdown = f" · next in {left}s"
    return "ok", f"Running · every {interval}s{countdown}"


def _empty_text() -> str:
    return "暂无记录。" if i18n.is_chinese() else "Nothing yet."


def _layout(active: str, title: str, content: str) -> str:
    dot, text = _status_line()
    tabs = []
    for key, label, href in (("status", "Status", "/"), ("setup", "Setup", "/setup"),
                             ("session", "Session", "/session")):
        tabs.append(f'<a href="{href}" class="{"on" if key == active else ""}">{label}</a>')
    session = cfg.session()
    folder = "—"
    try:
        folder = os.path.basename(agent.working_dir(session).rstrip("/")) or "/"
    except Exception:
        folder = "missing folder"
    page = f"""<!doctype html>
<html lang="{i18n.current()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · {APP_NAME}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⌂</text></svg>">
<style>{assets.CSS}</style>
</head>
<body data-empty="{escape(_empty_text())}">
<header class="top">
  <h1>{APP_NAME} <span class="ver">v{__version__}</span></h1>
  <div class="statusline"><span class="dot {dot}" id="status-dot"></span><span id="status-text">{escape(text)}</span></div>
  <div class="top-actions">
    <button class="theme" id="lang" data-post="/api/ui-lang"
            data-payload='{{"lang": "{i18n.toggle_to()}"}}'
            title="{i18n.title()}">{i18n.label()}</button>
    <button class="theme" id="theme" title="Toggle theme">☾</button>
  </div>
</header>
<nav class="tabs">{''.join(tabs)}</nav>
<main>{content}</main>
<footer>
  <span>{APP_NAME} · v{__version__} · local only (127.0.0.1)</span>
  <span>Session <code>{escape(session.get('sessionId') or '—')}</code> · {escape(folder)}</span>
</footer>
<div id="toast"></div>
<script>{assets.JS}</script>
</body>
</html>"""
    return i18n.apply(page)


def _last_reply_when(stamp: float | None) -> str:
    """When, not how long: the value above is the duration of that reply."""
    if not stamp:
        return "还没有回复过" if i18n.is_chinese() else "no reply yet"
    when = _ago(stamp)
    return f"{when}前" if i18n.is_chinese() else f"{when} ago"


def _auth_note() -> str:
    """The one thing people get wrong: the provider's credential is not the
    password they log in with, and POP3/SMTP have to be switched on first."""
    if i18n.is_chinese():
        return (
            "不是登录密码。请先在邮箱网页端开启 POP3/SMTP 服务，取得<b>授权码</b>后填在这里；"
            "收发共用这一份，设置一次即可。"
        )
    return (
        "Not your login password. Turn on POP3/SMTP in the mailbox's web settings first, then paste "
        "the <b>authorization code</b> the provider issues. One code covers sending and receiving, "
        "so it is set once."
    )


def _inout(received: int, replied: int) -> str:
    """Counted mail, with the two words in the page's language.

    The words are lowercase and two letters long, so they cannot go in the
    phrase table — "in" appears in half the prose on this page. Numbered values
    do not belong in a fixed table either. So they are built here.
    """
    if i18n.is_chinese():
        return f"{received} 收 · {replied} 发"
    return f"{received} in · {replied} out"


def _hour_labels(count: int) -> list[str]:
    now = datetime.now()
    labels = []
    for index in range(count):
        moment = now.timestamp() - (count - 1 - index) * 3600
        labels.append(datetime.fromtimestamp(moment).strftime("%H"))
    return labels


def _thinking_options(stored: str | None) -> list[tuple[str, str]]:
    """Two choices, not seven.

    "off" is a level; the empty value is not a level at all — it means pass no
    flag and let the pi session's own configuration decide. A stored level from
    an older config is shown as itself so the page does not lie about it, and
    disappears from the list the moment another option is picked.
    """
    off = ("off", "关闭" if i18n.is_chinese() else "Off")
    auto = ("", "由 Pi 模型会话自行设置" if i18n.is_chinese() else "As the pi session is configured")
    current = (stored or "").strip()
    if current in ("", "off"):
        return [off, auto]
    return [(current, current), off, auto]


def _token_placeholder() -> str:
    if i18n.is_chinese():
        return "未设置 — 粘贴邮箱的授权码"
    return "not set — paste the mailbox's authorization code"


def _checked(flag: bool) -> str:
    return " checked" if flag else ""


def _options(values: list[tuple[str, str]], selected: str) -> str:
    return "".join(
        f'<option value="{escape(value)}"{" selected" if value == selected else ""}>{escape(label)}</option>'
        for value, label in values
    )


def _token_field(name: str, token: str, label: str = "Authorization code") -> str:
    """Password-style field pre-filled with the stored token.

    The browser masks it natively, so a saved token reads as dots; the eye
    button flips it to plain text. This server only listens on 127.0.0.1 and
    has no authentication, so a token visible in the page is not a new
    exposure — anyone who can load this page can also read config.json. It is
    still the reason this server must never be exposed beyond localhost.
    """
    has_token = bool(token)
    return f"""<div class="field token-field">
      <label>{label}</label>
      <div class="token-wrap">
        <input name="{name}" type="password" value="{escape(token)}"
               placeholder="{escape(_token_placeholder())}" autocomplete="new-password">
        <button type="button" class="eye-btn" title="Show token"
                data-target="{name}"{"" if has_token else " disabled"}>👁</button>
      </div>
    </div>"""


def _lines(values) -> str:
    """List -> textarea content (one variant per line)."""
    if isinstance(values, str):
        return values
    return "\n".join(str(item) for item in (values or []))


# --------------------------------------------------------------------------- #
# Pairing card (shared by Status and Setup)
# --------------------------------------------------------------------------- #

def _pairing_card() -> str:
    if not cfg.is_configured():
        return ""
    from .. import crypto

    payload = crypto.build_pairing_payload()
    if not payload:
        return ""
    address = cfg.address()
    note = (
        "The code contains both key pairs and the transport settings. Treat it like a "
        "password: anyone who scans it can talk to this bridge, and if tools are enabled "
        "on the Session tab, can run commands on this Mac."
    )
    return f"""
<div class="card">
  <h2>Pairing <span class="hint">scan once in the Clutcha app · Remote tab</span></h2>
  <div class="pairing">
    <img src="/api/pairing.svg?t={int(time.time())}" alt="Pairing QR code" width="208" height="208"
         onerror="this.hidden=true;var f=document.getElementById('qr-fallback');if(f)f.hidden=false;">
    <div class="meta">
      <dl class="kv">
        <dt>Agent</dt><dd>{escape(cfg.monkey().get('name') or 'Monkey')}</dd>
        <dt>Address</dt><dd>{escape(address)}</dd>
        <dt>Session</dt><dd>{escape(cfg.session().get('sessionId') or '—')}</dd>
        <dt>Tools</dt><dd>{escape(_tools_label(cfg.session()))}</dd>
      </dl>
      <p class="note" id="qr-fallback" hidden style="color:var(--err);margin:12px 0 0">The QR code could not be
      rendered — reload the page. If it stays empty the <code>qrcode</code> package is missing: run
      install.command again.</p>
      <p class="note" style="margin-top:12px">{escape(note)}</p>
    </div>
  </div>
</div>"""


def _tools_label(session: dict) -> str:
    on = (session.get("tools") or "off") == "on"
    if i18n.is_chinese():
        return "开启" if on else "关闭（只回文字）"
    return "on" if on else "off (text only)"


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #

STATUS_JS = """
<script>
(function(){
  var ticks = 0;
  function set(id, value){ var el = document.getElementById(id); if (el && value !== undefined) el.textContent = value; }
  function escapeHtml(text){
    return String(text).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function refresh(){
    fetch('/api/live', {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(d){
      set('live-uptime', d.uptime);
      set('live-poll', d.poll);
      set('live-messages', d.messages);
      set('live-latency', d.latency);
      var dot = document.getElementById('status-dot');
      if (dot) dot.className = 'dot ' + d.dot;
      set('status-text', d.status);
      var body = document.getElementById('activity-body');
      if (body) {
        body.innerHTML = d.activity.map(function(row){
          return '<tr><td class="time">' + escapeHtml(row.time) + '</td><td><span class="tag ' +
            escapeHtml(row.kind) + '">' + escapeHtml(row.kind) + '</span></td><td>' +
            escapeHtml(row.message) + '</td></tr>';
        }).join('') || '<tr><td colspan="3" class="empty-state">' +
          (document.body.dataset.empty || 'Nothing yet.') + '</td></tr>';
      }
      ticks += 1;
      if (ticks % 2 === 0) {
        var charts = {'chart-messages': d.charts.messages, 'chart-polls': d.charts.polls};
        Object.keys(charts).forEach(function(id){
          var el = document.getElementById(id);
          if (el) el.innerHTML = charts[id];
        });
      }
    }).catch(function(){});
  }
  setInterval(refresh, 4000);
})();
</script>
"""


def status_page() -> str:
    snapshot = STATE.snapshot()
    rows = STATE.buckets(24)
    labels = _hour_labels(24)

    messages_chart = charts.grouped_bars(
        labels,
        [("In", [row["in"] for row in rows]), ("Out", [row["out"] for row in rows])],
        ["var(--accent)", "var(--warn)"],
    )
    polls_chart = charts.grouped_bars(
        labels,
        [("Replies", [row["ok"] for row in rows]), ("Empty", [row["empty"] for row in rows]),
         ("Errors", [row["error"] for row in rows])],
        ["var(--ok)", "var(--dim)", "var(--err)"],
    )
    latency = f"{snapshot['lastReplyMs']:.0f} ms" if snapshot.get("lastReplyMs") else "—"
    info = agent.session_info(cfg.session())
    poll_age = _ago(snapshot.get("lastPollAt"))

    activity = []
    for entry in snapshot["log"][:40]:
        activity.append(
            f'<tr><td class="time">{escape(entry["time"][11:])}</td>'
            f'<td><span class="tag {escape(entry["kind"])}">{escape(entry["kind"])}</span></td>'
            f'<td>{escape(entry["message"])}</td></tr>'
        )
    if not activity:
        activity.append('<tr><td colspan="3" class="empty-state">Nothing yet.</td></tr>')

    setup_banner = ""
    if not snapshot["configured"]:
        setup_banner = (
            '<div class="card" style="border-color:var(--warn)">'
            '<h2>Waiting for setup</h2>'
            '<p class="note">This bridge has not sent or received anything yet. '
            'Open <a href="/setup">Setup</a>, fill in your mailbox, save — then scan the '
            'pairing code with the Clutcha app.</p></div>'
        )

    flow = """
<section class="card flow">
  <h2>How it fits together <span class="hint">this page is the middle box</span></h2>
  <div class="flow-row">
    <div class="node"><b>Clutcha App</b><span>the phone</span></div>
    <div class="arrow">encrypted letter&nbsp;▶</div>
    <div class="node"><b>mailbox</b><span>sees only armor</span></div>
    <div class="arrow">▶</div>
    <div class="node here"><b>Clutcha Bridge</b><span>this program</span></div>
    <div class="arrow">▶</div>
    <div class="node"><b>pi session</b><span>the agent</span></div>
  </div>
  <p class="note">The answer comes back the same way, and both letters are sealed before they
  reach the mailbox. Nothing here listens on the network: an email account is the transport,
  which is why there is no port to open and no server to rent.</p>
</section>
"""

    content = f"""
{setup_banner}

{flow}
<section class="grid">
  <div class="card tight stat">
    <div class="label">Service</div>
    <div class="value small" id="live-uptime">{_uptime(snapshot['uptime'])}</div>
    <div class="sub">pid {os.getpid()} · started {datetime.fromtimestamp(snapshot['startedAt']).strftime('%H:%M')}</div>
  </div>
  <div class="card tight stat">
    <div class="label">Last check</div>
    <div class="value small" id="live-poll">{escape(str(snapshot['lastPollResult']))}</div>
    <div class="sub">{poll_age} · {snapshot['polls']} checks total</div>
  </div>
  <div class="card tight stat">
    <div class="label">Messages</div>
    <div class="value" id="live-messages">{_inout(snapshot['received'], snapshot['replied'])}</div>
    <div class="sub">{snapshot['errors']} error(s)</div>
  </div>
  <div class="card tight stat">
    <div class="label">Last reply</div>
    <div class="value small" id="live-latency">{latency}</div>
    <div class="sub">{_last_reply_when(snapshot.get('lastReplyAt'))}</div>
  </div>
</section>

<div class="grid two">
  <div class="card">
    <h2>Messages <span class="hint">last 24h</span></h2>
    <div class="chart" id="chart-messages">{messages_chart}</div>
    <div class="legend">{charts.legend([("In", "var(--accent)"), ("Out", "var(--warn)")])}</div>
  </div>
  <div class="card">
    <h2>Poll results <span class="hint">last 24h</span></h2>
    <div class="chart" id="chart-polls">{polls_chart}</div>
    <div class="legend">{charts.legend([("Replies", "var(--ok)"), ("Empty", "var(--dim)"), ("Errors", "var(--err)")])}</div>
  </div>
</div>

<div class="card">
  <h2>Activity <span class="hint"><button data-post="/api/poll-now" style="padding:5px 11px;font-size:12px">Check now</button></span></h2>
  <div class="scroll">
    <table>
      <thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead>
      <tbody id="activity-body">{''.join(activity)}</tbody>
    </table>
  </div>
</div>
{STATUS_JS}
"""
    return _layout("status", "Status", content)


def status_live() -> dict:
    snapshot = STATE.snapshot()
    rows = STATE.buckets(24)
    labels = _hour_labels(24)
    dot, text = _status_line()
    return {
        "uptime": _uptime(snapshot["uptime"]),
        "poll": snapshot["lastPollResult"],
        "pollAge": _ago(snapshot.get("lastPollAt")),
        "polls": snapshot["polls"],
        "messages": _inout(snapshot["received"], snapshot["replied"]),
        "errors": snapshot["errors"],
        "latency": f"{snapshot['lastReplyMs']:.0f} ms" if snapshot.get("lastReplyMs") else "—",
        "dot": dot,
        "status": text,
        "charts": {
            "messages": charts.grouped_bars(
                labels,
                [("In", [row["in"] for row in rows]), ("Out", [row["out"] for row in rows])],
                ["var(--accent)", "var(--warn)"],
            ),
            "polls": charts.grouped_bars(
                labels,
                [("Replies", [row["ok"] for row in rows]), ("Empty", [row["empty"] for row in rows]),
                 ("Errors", [row["error"] for row in rows])],
                ["var(--ok)", "var(--dim)", "var(--err)"],
            ),
        },
        "activity": [
            {"time": entry["time"][11:], "kind": entry["kind"], "message": entry["message"]}
            for entry in snapshot["log"][:40]
        ],
    }


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #

def setup_page() -> str:
    mail = cfg.me_mail()
    inbox = mail.get("inbox") or {}
    smtp = mail.get("smtp") or {}
    poll = cfg.poll_cfg()
    configured = cfg.is_configured()

    banner = ""
    if not configured:
        banner = (
            '<div class="card" style="border-color:var(--warn)">'
            '<h2>Setup needed</h2>'
            '<p class="note">Fill in your mailbox below and save. Both key pairs are minted on '
            'first run, so pairing works as soon as the mailbox is reachable. '
            'Use an app-specific token, not your account password.</p></div>'
        )

    content = f"""
{banner}

<form class="card" data-api="/api/me">
  <h2>Communication mailbox <span class="hint">the address the app writes to and reads from</span></h2>
  <div class="row">
    <div class="field"><label>Name <span style="color:var(--dim)">— this Mac's name</span></label>
      <input name="agent_name" value="{escape(cfg.monkey().get('name') or '')}" placeholder="{escape(cfg.default_agent_name())}">
      <p class="note" style="margin:4px 0 0">Letters are signed with it, and the phone shows it as the
      machine that answered. The app itself is called Clutcha, so repeating that here only blurs
      which end is which. Changing it reaches the phone the next time you pair.</p></div>
    <div class="field"><label>Email address</label>
      <input name="address" value="{escape(mail.get('address') or '')}" placeholder="you@example.com"></div>
  </div>


  <h2 style="margin-top:8px">Inbox <span class="hint">POP3 or IMAP</span></h2>
  <div class="row">
    <div class="field"><label>Protocol</label>
      <select name="inbox_protocol">{_options([("pop3", "POP3"), ("imap", "IMAP")], inbox.get("protocol", "pop3"))}</select></div>
    <div class="field"><label>Host</label>
      <input name="inbox_host" value="{escape(inbox.get('host') or '')}" placeholder="pop.example.com"></div>
    <div class="field"><label>Port</label>
      <input name="inbox_port" value="{escape(str(inbox.get('port') or ''))}" placeholder="995"></div>
  </div>
  <div class="checks">
    <label><input type="checkbox" name="inbox_ssl"{_checked(bool(inbox.get('useSSL', True)))}> SSL / TLS</label>
    <label><input type="checkbox" name="inbox_starttls"{_checked(bool(inbox.get('starttls')))}> STARTTLS</label>
  </div>

  <h2>Outgoing mail <span class="hint">SMTP</span></h2>
  <div class="row">
    <div class="field"><label>Host</label>
      <input name="smtp_host" value="{escape(smtp.get('host') or '')}" placeholder="smtp.example.com"></div>
    <div class="field"><label>Port</label>
      <input name="smtp_port" value="{escape(str(smtp.get('port') or ''))}" placeholder="465"></div>
  </div>

  {_token_field("mail_token", (inbox.get('token') or smtp.get('token') or ''))}
  <p class="note" style="margin:-6px 0 14px">{_auth_note()}</p>
  <div class="checks">
    <label><input type="checkbox" name="smtp_ssl"{_checked(bool(smtp.get('useSSL', True)))}> SSL / TLS</label>
    <label><input type="checkbox" name="smtp_starttls"{_checked(bool(smtp.get('starttls')))}> STARTTLS</label>
  </div>

  <div class="actions">
    <button class="primary" type="submit">Save</button>
    <button type="button" data-post="/api/test-mailbox" data-output="test-output">Test connection</button>
  </div>
  <pre id="test-output" hidden style="margin-top:12px"></pre>
  <p class="note" style="margin-top:10px">The login name is the address above. One mailbox for
  both sides: the app writes to it, the bridge answers in it.</p>
</form>

{_pairing_card()}

{_letter_card()}

<form class="card" data-api="/api/poll-config">
  <h2>Poll interval <span class="hint">how often the mailbox is checked</span></h2>
  <div class="row">
    <div class="field"><label>Interval (seconds, 60–3600)</label>
      <input name="intervalSeconds" value="{escape(str(poll.get('intervalSeconds') or cfg.DEFAULT_POLL_SECONDS))}"></div>
    <div class="field"><label>Examine at most (new messages per check)</label>
      <input name="maxScan" value="{escape(str(poll.get('maxScan') or 20))}"></div>
  </div>
  <div class="checks">
    <label><input type="checkbox" name="enabled"{_checked(bool(poll.get('enabled', True)))}> Polling enabled</label>
  </div>
  <div class="actions">
    <button class="primary" type="submit">Save</button>
    <button type="button" data-post="/api/poll-now">Check now</button>
  </div>
  <p class="note" style="margin-top:10px">Mail delivery is not instant — a message often takes
  about a minute to appear in the inbox. The app fetches on demand, so this interval only
  decides how quickly the bridge notices something new.</p>
</form>

{_cleanup_card()}
"""
    return _layout("setup", "Setup", content)


def _cleanup_card() -> str:
    block = cfg.cleanup_cfg()
    from .. import cleanup

    state = cleanup.load_state()
    last = ""
    if state.get("lastRun"):
        last = (
            f"上次清理 {state['lastRun']}，删除 {state.get('deleted', 0)} 封。"
            if i18n.is_chinese()
            else f"Last run {state['lastRun']}: {state.get('deleted', 0)} deleted."
        )
    hours = [(str(hour), f"{hour:02d}:00") for hour in cleanup.HOURS]
    return f"""
<form class="card" data-api="/api/cleanup">
  <h2>Automatic cleanup <span class="hint">delete yesterday's letters once a day</span></h2>
  <div class="row">
    <div class="field"><label>Cleanup</label>
      <div class="checks" style="margin:9px 0 0">
        <label><input type="checkbox" name="enabled"{_checked(bool(block.get('enabled')))}>
          Run once a day</label>
      </div>
    </div>
    <div class="field"><label>At</label>
      <select name="hour">{_options(hours, str(block.get('hour') or 3))}</select></div>
  </div>
  <p class="note">{_cleanup_note()}</p>
  {f'<p class="note" style="margin-top:-6px">{escape(last)}</p>' if last else ''}
  <div class="actions">
    <button class="primary" type="submit">Save</button>
    <button type="button" data-dialog="cleanup-log">View log</button>
  </div>
</form>
{_cleanup_log_dialog()}"""


def _cleanup_log_dialog() -> str:
    """Runs recorded on disk, newest first.

    A native <dialog>: it traps focus and closes on Escape for free, which is
    what a log popped open from a settings page should do.
    """
    from .. import cleanup

    rows = cleanup.load_log()
    if rows:
        body = "".join(
            "<tr>"
            f"<td class='time'>{escape(row.get('at') or '')}</td>"
            f"<td>{escape(str(row.get('target') or ''))}</td>"
            f"<td>{'✓' if row.get('ok') else '✗'} {escape(str(row.get('deleted', 0)))}</td>"
            f"<td>{escape(str(row.get('examined', 0)))}</td>"
            f"<td>{escape(str(row.get('error') or ''))}</td>"
            "</tr>"
            for row in rows
        )
    else:
        body = (
            "<tr><td colspan='5' class='empty-state'>"
            + ("还没有清理记录。" if i18n.is_chinese() else "Nothing has been cleaned yet.")
            + "</td></tr>"
        )
    return f"""
<dialog id="cleanup-log">
  <h2>{('清理日志' if i18n.is_chinese() else 'Cleanup log')}
    <span class="hint">{('最近 ' + str(len(rows)) + ' 次') if rows else ''}</span></h2>
  <div class="scroll">
    <table>
      <thead><tr>
        <th>{('时间' if i18n.is_chinese() else 'When')}</th>
        <th>{('清理的信件日期' if i18n.is_chinese() else 'Letter date')}</th>
        <th>{('删除' if i18n.is_chinese() else 'Deleted')}</th>
        <th>{('检查' if i18n.is_chinese() else 'Examined')}</th>
        <th>{('错误' if i18n.is_chinese() else 'Error')}</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>
  <div class="actions" style="margin-top:12px">
    <button type="button" class="primary" data-close-dialog="cleanup-log">
      {('关闭' if i18n.is_chinese() else 'Close')}</button>
  </div>
</dialog>"""


def _cleanup_note() -> str:
    if i18n.is_chinese():
        return (
            "只删<b>昨天</b>的、<b>已经读过</b>的、<b>本协议自己的信件</b>（app 发来的和 bridge 回的）。"
            "真正的邮件、今天到的信、bridge 还没读过的信，一概不动。默认关闭 —— 删信这种事不该是事后才知道的。"
        )
    return (
        "It only deletes letters from <b>yesterday</b> that have <b>already been read</b> and that "
        "<b>belong to this protocol</b> — the app's letters and the bridge's replies. Real email, "
        "anything from today, and anything the bridge has not read yet is left alone. Off by "
        "default: deleting mail is not something to discover afterwards."
    )


def _letter_card() -> str:
    letter = cfg.mail_template()
    preview = letter_template.preview(letter, cfg.monkey().get("name") or "Monkey")
    problems = preview["problems"]
    warnings = preview["warnings"]

    issues = ""
    if problems:
        issues = (
            '<div class="note" style="color:var(--err); margin-bottom:12px">'
            + "<br>".join(escape(item) for item in problems)
            + "</div>"
        )

    # Both languages are on screen at once: the Language select only decides
    # which one gets used, and a tab strip that hid half the fields made the
    # other half easy to forget.
    # Both languages stay in the document but only one is visible: the Language
    # select switches them without a save, and a hidden block still submits, so
    # saving the visible one never blanks the other.
    resolved = letter_template.resolve_lang(letter)
    blocks = []
    for code, label in (("zh", "中文"), ("en", "English")):
        shown = "" if code == resolved else " hidden"
        blocks.append(f"""
  <div class="lang-block" data-letter-lang="{code}"{shown}>
    <div class="field"><label>Subject · {label}</label>
      <input name="subject_{code}" value="{escape((letter.get('subject') or {}).get(code) or '')}"></div>
    <div class="field"><label>Greeting variants · one per line, picked at random</label>
      <textarea name="greeting_{code}" rows="5">{escape(_lines((letter.get('greeting') or {}).get(code)))}</textarea></div>
    <div class="field"><label>Letter body · must contain <code>{{armored}}</code></label>
      <textarea name="body_{code}" rows="4">{escape((letter.get('body') or {}).get(code) or '')}</textarea></div>
    <div class="field"><label>Closing variants · one per line, blank allowed</label>
      <textarea name="closing_{code}" rows="5">{escape(_lines((letter.get('closing') or {}).get(code)))}</textarea></div>
  </div>""")

    previews = []
    for code in ("zh", "en"):
        one = letter_template.preview(letter, cfg.monkey().get("name") or "Clutcha", lang=code)
        shown = "" if code == resolved else " hidden"
        previews.append(f"""
  <div class="letter-preview" data-letter-lang="{code}"{shown}>
    <dl class="kv">
      <dt>Language</dt><dd>{escape(code)}</dd>
      <dt>Subject</dt><dd>{escape(one['subject'])}</dd>
    </dl>
    <pre>{escape(one['body'])}</pre>
  </div>""")

    warn_html = ""
    if warnings:
        warn_html = (
            '<p class="note" style="margin-top:0">'
            + "<br>".join(escape(item) for item in warnings)
            + "</p>"
        )

    return f"""
<form class="card" data-api="/api/letter">
  <h2>Letter template <span class="hint">the wrapper around the ciphertext</span></h2>
  <div class="row">
    <div class="field"><label>Language</label>
      <select name="lang" data-resolved="{escape(resolved)}">{_options(list(letter_template.LANG_LABELS), letter.get('lang') or 'auto')}</select></div>
    <div class="field"><label>Vary the wording</label>
      <div class="checks" style="margin:9px 0 0">
        <label><input type="checkbox" name="vary"{_checked(bool(letter.get('vary', True)))}>
          Pick a random greeting and closing each time</label>
      </div>
    </div>
  </div>

  {issues}
  {''.join(blocks)}

  {warn_html}
  <p class="note">{_placeholders_note()}</p>

  <h2 style="margin-top:18px">{_preview_title()}</h2>
  {''.join(previews)}

  <div class="actions">
    <button class="primary" type="submit">Save</button>
  </div>
</form>
"""


def _placeholders_note() -> str:
    if i18n.is_chinese():
        return (
            "占位符：<code>{armored}</code>（必需，且只能出现一次 —— 密文就插在它的位置）、"
            "<code>{time}</code>、<code>{agent}</code>。其余内容随你写。"
            "不要重新缩进这个块、不要套 HTML、不要改动它的行宽：app 是逐字匹配的，改了位置就找不到。"
        )
    return (
        "Placeholders: <code>{armored}</code> (required, exactly once — the ciphertext is inserted "
        "where it sits), <code>{time}</code>, <code>{agent}</code>. Everything else is yours. Do not "
        "re-indent the block, wrap it in HTML, or change its line width: the app looks for the block "
        "verbatim and will not find it otherwise."
    )


def _preview_title() -> str:
    return "信件预览" if i18n.is_chinese() else "Letter preview"


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #

def session_page() -> str:
    session = cfg.session()
    info = agent.session_info(session)
    command = agent.display_command(session, "Hello from the app")
    placement = agent.check_cwd(session.get("cwd") or "")
    mode = session.get("mode") or "simple"
    limit = service.reply_limit()
    updated = datetime.fromtimestamp(info["updated"]).strftime("%Y-%m-%d %H:%M") if info.get("updated") else "—"
    size = f"{info['bytes'] / 1024:.0f} KB" if info.get("bytes") else "—"
    folder = placement["path"] if placement.get("ok") else "missing folder"
    if not (session.get("cwd") or "").strip():
        folder = f"empty — runs in the bridge folder: {folder}"
    placeholders = ", ".join(f"<code>{{{name}}}</code>" for name in agent.PLACEHOLDERS)

    return _layout("session", "Session", f"""
<form class="card" data-api="/api/session">
  <h2>Session <span class="hint">the bridge's own conversation</span></h2>

  <div class="row">
    <div class="field"><label>Session ID <span style="color:var(--dim)">— the bridge's own</span></label>
      <input name="sessionId" class="mono" value="{escape(session.get('sessionId') or '')}" placeholder="clutcha-main">
      <p class="note" style="margin:4px 0 0">pi creates it on the first message. Do not point this at a
      conversation you have open in the terminal — a session id is a name, and reusing one merges two
      conversations. Changing the id or the folder starts a different one.</p></div>
    <div class="field"><label>Model</label>
      <input name="model" class="mono" value="{escape(session.get('model') or '')}"
             placeholder="pi's default">
      <p class="note" style="margin:4px 0 0">Passed as <code>--model</code>, exactly as typed.
      Local or remote is pi's business, not the bridge's.</p></div>
  </div>

  <div class="row">
    <div class="field">
      <label>Working directory</label>
      <div class="token-wrap">
        <input name="cwd" class="mono" value="{escape(session.get('cwd') or '')}" placeholder="{escape(cfg.BRIDGE_DIR)}">
        <button type="button" class="eye-btn" style="width:auto;padding:0 12px;font-size:12.5px"
                data-post="/api/session/check-cwd" data-from="cwd" data-output="cwd-output">Check</button>
      </div>
      <p class="note" style="margin:4px 0 0" id="cwd-output">{escape(folder)}</p>
    </div>
  </div>

  <div class="row">
    <div class="field"><label>Thinking</label>
      <select name="thinking">{_options(_thinking_options(session.get('thinking')), session.get('thinking') or 'off')}</select></div>
    <div class="field"><label>Timeout (seconds)</label>
      <input name="timeoutSeconds" value="{escape(str(session.get('timeoutSeconds') or 300))}">
      <p class="note" style="margin:4px 0 0">How long a reply may take before the bridge gives up and sends the fallback.</p></div>
    <div class="field"><label>Reply limit (characters)</label>
      <input name="replyMaxChars" value="{escape(str(limit))}">
      <p class="note" style="margin:4px 0 0">Longer answers are cut here; the full text stays on the Mac.</p></div>
  </div>

  <div class="field">
    <label>Fallback reply <span style="color:var(--dim)">— sent when the agent fails or times out</span></label>
    <input name="fallback" value="{escape(session.get('fallback') or '')}" placeholder="(empty: say nothing)"></div>

  <details class="advanced">
    <summary>Advanced</summary>
    <div class="checks" style="margin-top:12px">
      <label><input type="checkbox" name="tools"{_checked((session.get('tools') or 'off') == 'on')}>
        Let the agent use tools</label>
    </div>
    <p class="note" style="margin:-4px 0 14px">Off adds <code>-nt</code>: the agent can only answer with text.
      On adds nothing, so whatever your pi configuration allows becomes reachable from a paired phone —
      including <code>bash</code>. There is no approval step and no login: the mailbox is the only door.</p>

    <div class="field">
      <label>System prompt <span style="color:var(--dim)">— optional, appended to pi's own</span></label>
      <textarea name="systemPrompt" rows="3" placeholder="Optional persona…">{escape(session.get('systemPrompt') or '')}</textarea>
    </div>
    <div class="field">
      <label>Command source</label>
      <select name="mode">{_options([("simple", "Built from these fields"), ("raw", "Hand-written command")],
                                       mode)}</select>
    </div>
    <div class="field" data-control="mode" data-show-when="raw">
      <label>Command line <span style="color:var(--dim)">— placeholders: {placeholders}</span></label>
      <textarea name="command" class="mono" rows="4">{escape(session.get('command') or '')}</textarea>
      <p class="note" style="margin:4px 0 0">Runs as argv, no shell. Switching back to "built from these fields"
      discards whatever you wrote here.</p>
    </div>
  </details>

  <div class="actions">
    <button class="primary" type="submit">Save</button>
    <button type="button" data-post="/api/session/preview"
            data-from="mode,sessionId,model,cwd,thinking,tools,systemPrompt,command"
            data-output="preview-box">Preview command</button>
    <button type="button" data-post="/api/session/test" data-output="test-box">Test session</button>
  </div>
  <pre id="preview-box" style="margin-top:12px">{escape(command)}</pre>
  <pre id="test-box" hidden style="margin-top:12px"></pre>
</form>

<div class="card">
  <h2>Long answers <span class="hint">why replies get cut</span></h2>
  <dl class="kv">
    <dt>Limit</dt><dd class="prose">{limit} characters. The ciphertext is base64 (+33%) and the mail provider
      has a size limit, so a huge answer would not arrive at all.</dd>
    <dt>What happens</dt><dd class="prose">The reply is cut, a marker is appended, and the complete text is
      written to <code>{escape(cfg.STATE_DIR)}/replies/</code> on this computer.</dd>
    <dt>Timeout</dt><dd class="prose">{escape(str(session.get('timeoutSeconds') or 300))} seconds. Tool-heavy turns
      take longer than chat; if replies stop arriving, raise this first.</dd>
    <dt>If it fails</dt><dd class="prose">The fallback reply is sent instead of nothing, so the phone never
      just goes quiet. The reason lands in the Status tab.</dd>
  </dl>
</div>

<div class="card">
  <h2>Session state <span class="hint">{escape('pi session file' if session.get('harness', 'pi') == 'pi' else 'managed by the command')}</span></h2>
  <dl class="kv">
    <dt>File</dt><dd>{escape(info.get('path') or 'not created yet')}</dd>
    <dt>Size</dt><dd>{size}</dd>
    <dt>Turns</dt><dd>{info.get('turns') or 0}</dd>
    <dt>Updated</dt><dd>{updated}</dd>
  </dl>
  <div class="actions">
    <button type="button" data-post="/api/session/reset">Archive session</button>
  </div>
  <p class="note" style="margin-top:10px">Archiving renames the session file (it stays on disk),
  so the next message starts a fresh conversation.</p>
</div>
""")
