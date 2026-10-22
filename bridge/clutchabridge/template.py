"""The letter that carries the ciphertext.

The app and the bridge only look for the `-----BEGIN VM MESSAGE-----` block;
everything around it is decoration. That decoration still matters: an empty or
byte-identical letter is scored more harshly by spam filters, so greetings and
closings vary by default and the user can edit the whole thing.

Three rules the renderer enforces, because breaking any of them makes the mail
undeliverable rather than merely ugly:

1. the armor block goes in verbatim — no rewrapping, no indenting, no quoting
2. the letter is plain text, UTF-8; the SMTP layer sends `8bit`
3. `{armored}` must appear exactly once, or the code refuses to save
"""

from __future__ import annotations

import os
import random
import time

# Placeholders a user may put in the body. `{armored}` is mandatory.
PLACEHOLDERS = ("time", "armored", "agent")
REQUIRED_PLACEHOLDER = "armored"

LANGS = ("zh", "en")
LANG_LABELS = (("auto", "Auto (system)"), ("zh", "中文"), ("en", "English"))

_TIME_FORMAT = {"zh": "%Y年%m月%d日 %H:%M", "en": "%Y-%m-%d %H:%M"}

SAMPLE_LINE = ("Zm9vYmFyYmF6cXV4" * 4)[:64]
SAMPLE_ARMOR = "\n".join(
    ["-----BEGIN VM MESSAGE-----"] + [SAMPLE_LINE] * 6 + ["-----END VM MESSAGE-----"]
)


# --------------------------------------------------------------------------- #
# Language
# --------------------------------------------------------------------------- #

def system_lang() -> str:
    """Chinese if the machine is Chinese, English otherwise."""
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (os.environ.get(key) or "").lower()
        if value.startswith("zh"):
            return "zh"
        if value.startswith("en"):
            return "en"
    try:
        import locale

        code = (locale.getdefaultlocale()[0] or "").lower()
        if code.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


def resolve_lang(template: dict) -> str:
    lang = str((template or {}).get("lang") or "auto").lower()
    return lang if lang in LANGS else system_lang()


def _for_lang(block: dict, lang: str) -> str:
    """Pull one language out of a {lang: text} block, falling back to any."""
    if not isinstance(block, dict):
        return ""
    if block.get(lang):
        return str(block[lang])
    for key in LANGS:
        if block.get(key):
            return str(block[key])
    return ""


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _pick(options) -> str:
    """One of the variants, or the first when the list is a plain string."""
    if isinstance(options, str):
        return options
    values = [str(item) for item in (options or [])]
    if not values:
        return ""
    return random.choice(values)


def _fill(text: str, values: dict) -> str:
    out = text
    for key in values:
        out = out.replace("{" + key + "}", values[key])
    return out


def subject(template: dict, lang: str | None = None) -> str:
    template = template or {}
    resolved = lang or resolve_lang(template)
    value = _for_lang(template.get("subject") or {}, resolved).strip()
    return value or "Clutcha message"


def body(template: dict, armored: str, agent_name: str = "Monkey", lang: str | None = None) -> str:
    """Greeting, note, ciphertext, closing — in that order, blank-line separated."""
    template = template or {}
    resolved = lang or resolve_lang(template)
    vary = bool(template.get("vary", True))

    def choose(block: dict) -> str:
        options = block.get(resolved)
        if isinstance(options, str):
            return options
        values = list(options or [])
        if not values:
            return ""
        return random.choice(values) if vary else values[0]

    stamp = time.strftime(_TIME_FORMAT.get(resolved, _TIME_FORMAT["en"]))
    note = _for_lang(template.get("body") or {}, resolved)
    note = _fill(note, {"time": stamp, "agent": agent_name})

    # The placeholder decides where the ciphertext sits. A hand-edited
    # config.json without it would otherwise produce a letter with no message
    # in it, which the app silently ignores — so fall back to appending.
    token = "{" + REQUIRED_PLACEHOLDER + "}"
    if token in note:
        note = note.replace(token, armored.strip())
        parts = [
            choose(template.get("greeting") or {}).strip(),
            note.strip(),
            choose(template.get("closing") or {}).strip(),
        ]
    else:
        parts = [
            choose(template.get("greeting") or {}).strip(),
            note.strip(),
            armored.strip(),
            choose(template.get("closing") or {}).strip(),
        ]
    return "\n\n".join(part for part in parts if part) + "\n"


# --------------------------------------------------------------------------- #
# Validation (the page refuses to save a letter that cannot arrive)
# --------------------------------------------------------------------------- #

def _t(zh: str, en: str) -> str:
    """One sentence in the page's language.

    These lines surface both on the Setup card and in the toast after a failed
    save, so they follow the UI language rather than being English glue under a
    Chinese page. Imported here rather than at module level: web.i18n reads the
    config, and this module must stay loadable without the web layer.
    """
    try:
        from .web import i18n

        return zh if i18n.is_chinese() else en
    except Exception:
        return en


def problems(template: dict) -> list[str]:
    template = template or {}
    found: list[str] = []
    if not subject(template):
        found.append(_t("主题是空的。", "Subject is empty."))
    for lang in LANGS:
        note = _for_lang(template.get("body") or {}, lang)
        if not note:
            found.append(_t(f"信件正文（{lang}）是空的。", f"Letter body ({lang}) is empty."))
            continue
        count = note.count("{" + REQUIRED_PLACEHOLDER + "}")
        if count == 0:
            found.append(_t(
                f"信件正文（{lang}）里没有 {{armored}} 占位符 —— 这样一条消息都发不出去。",
                f"Letter body ({lang}) has no {{armored}} placeholder — nothing would be sent.",
            ))
        elif count > 1:
            found.append(_t(
                f"信件正文（{lang}）里 {{armored}} 出现了 {count} 次，只能是 1 次。",
                f"Letter body ({lang}) has {{armored}} {count} times; it must appear once.",
            ))
        lowered = note.lower()
        if "<html" in lowered or "<div" in lowered or "<br" in lowered:
            found.append(_t(
                f"信件正文（{lang}）看起来是 HTML；信件必须是纯文本。",
                f"Letter body ({lang}) looks like HTML; the letter must be plain text.",
            ))
    return found


def warnings(template: dict) -> list[str]:
    template = template or {}
    found: list[str] = []
    if not bool(template.get("vary", True)):
        found.append(_t(
            "关闭了措辞变换：每封信一字不差，容易被判成垃圾邮件。",
            "Varying is off: every letter is byte-identical, which spam filters dislike.",
        ))
    active = resolve_lang(template)
    if (template.get("lang") or "auto") == "auto":
        found.append(_t(
            f"语言跟随系统区域设置；这台电脑解析为「{active}」。",
            f"Language follows the system locale; this machine resolves to “{active}”.",
        ))
    return found


def preview(template: dict, agent_name: str = "Monkey", lang: str | None = None) -> dict:
    """One language's letter, ready to show.

    `lang` is for the page, which keeps both previews in the document so the
    Language select can switch without a round trip. Without it the template's
    own resolution wins, which is what the API and the test letter use.
    """
    resolved = (lang or resolve_lang(template)).strip().lower()
    if resolved not in LANGS:
        resolved = resolve_lang(template)
    return {
        "lang": resolved,
        "subject": subject(template, resolved),
        "body": body(template, SAMPLE_ARMOR, agent_name, resolved),
        "problems": problems(template),
        "warnings": warnings(template),
    }
