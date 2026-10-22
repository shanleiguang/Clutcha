# Clutcha Bridge

The computer half of Clutcha. The phone app encrypts a message and sends it to
your own mailbox; this bridge picks it up, opens it, hands the plaintext to a
command line on your computer, encrypts the answer and sends it back. Nothing
leaves your machine in clear text, and no server of ours is involved — there is
no "ours".

```
Clutcha app ──encrypted mail──▶ your mailbox ──POP3/IMAP──▶ Clutcha Bridge
     ▲                                                        │ argv
     └──────────────encrypted reply◀──mailbox◀────────────────┘ agent (pi)
```

The bridge is **transport only**. It has no conversation memory, no prompt
engineering and no model of its own: the session is a command line, a session
id and a working directory. Tools, model and memory belong to `pi` (or whatever
CLI you configure).

---

## 1. What you need

| | |
|---|---|
| Computer | macOS 12+, Linux, or Windows 10+ — plain Python, nothing here is platform-specific |
| Python | 3.9+ (`python3 --version`; `xcode-select --install` if missing) |
| Mailbox | one address you can read with POP3 or IMAP and send with SMTP |
| Mail token | an **app-specific password**, not your account password |
| Agent | `pi` on your `PATH`, or any CLI that takes a prompt and prints an answer |
| App | Clutcha on iOS, with the Remote tab unlocked |

Both sides share one mailbox: the app writes to it, the bridge answers in it.
That is deliberate — cross-domain mail gets scored as spam, self-send does not.

---

## 2. Install (four steps)

1. Download and unzip this folder (anywhere; `~/Applications` is fine).
2. Double-click **`install.command`** — creates `.venv` and installs two packages.
3. Double-click **`start.command`** — a browser opens on the Setup tab.
4. Fill in your mailbox, **Save**, then scan the pairing code with the app.

> **macOS will complain about `install.command`** ("cannot be opened because it
> is from an unidentified developer"). Right-click → **Open** → Open, once per
> script. Or, in Terminal, in this folder:
> `xattr -dr com.apple.quarantine .`

If something is missing, `start.command` says which step you skipped.

---

## 3. The three tabs

**Status** — is it running, when did it last check the mailbox or fail, how many
messages in and out, reply latency, and a live activity log. Monitoring only:
nothing is configured from here.

**Setup** — the mailbox (address, POP3/IMAP host, SMTP host, token), the pairing
code, the letter that carries the ciphertext, and the polling interval
(60–3600s, default 180). "Test connection" checks both directions without
sending anything.

**Session** — six fields, not a control panel: the session id, the model, the
working directory, the thinking level, the timeout, and how long a reply may
be. Each one is passed to `pi` as a flag; nothing else is set, so the agent
behaves the way your own `pi` does. The command line that will actually run is
shown at the bottom — preview it before trusting it.

---

## 4. The letter

Every message rides inside an email whose only important part is the
`-----BEGIN VM MESSAGE-----` block. Everything around it is decoration, and
decoration matters: byte-identical bulk mail is scored more harshly, so the
greeting and closing are picked at random from your lists.

You can edit, per language:

| Field | Notes |
|---|---|
| Subject | per language |
| Greeting / Closing | several variants, one per line, chosen at random |
| Body | free text, must contain `{armored}` exactly once |

Placeholders: `{armored}` (the ciphertext), `{time}`, `{agent}`.

Three rules, enforced when you save:

1. the armor block goes in **verbatim** — no re-indenting, no HTML, no reflowing
2. the letter is plain text UTF-8; the SMTP layer sends `8bit`
3. `{armored}` must appear once; without it nothing would be sent

"Preview" shows exactly what lands in the inbox. "Send a test letter to myself"
is a real message — one round trip, once per change, not in a loop.

**Language** is `Auto (system)` by default: Chinese if your computer is Chinese,
English otherwise. Set it explicitly if you want to be sure.

---

## 5. The session

The bridge owns its own session. The id is just a name: `pi` creates it on the
first message, and from then on every letter from the phone continues it. There
is one way in — the Session tab.

Do **not** point it at a conversation you have open in your terminal. A session
id is a name, not a handle: reusing one merges two conversations that were not
meant to meet, and the terminal side then sees the phone's messages as its own
history. Changing the id or the working directory starts a different session.

**Model.** The field is passed as `--model` exactly as typed. The bridge has no
opinion about which models exist, whether they are local or in the cloud, or
what their sampling parameters are — that is `pi`'s configuration:

```
~/.pi/agent/settings.json    defaultProvider / defaultModel / defaultThinkingLevel
~/.pi/agent/models.json      per-model samplingParams (temperature, top_p, …)
~/.pi/agent/auth.json        keys for the providers
```

Leave it empty and `pi`'s default is used. A typo is not caught here: run
"Test session" and the model server's own error comes back, verbatim.

**A fresh install starts clean.** On the very first run the bridge records the
mailbox as it is and answers none of it, and it archives any `pi` session that
already exists for the chosen id — a new deployment owes nothing to a
conversation it never had. The same archive happens if the previous process was
killed mid-turn, because an unanswered question left in a session is what makes
the next reply answer the wrong letter.

**Three knobs worth setting:**

| Field | Why |
|---|---|
| Timeout | Tool-heavy turns take minutes. If replies stopped arriving, raise this before anything else |
| Reply limit | Answers longer than this are cut. The ciphertext grows 33% in armor, and the provider has a size limit, so a huge answer would not arrive at all |
| Model | Pin the bridge to one model while your terminal keeps another. Empty means "whatever `pi` defaults to". A typo is not caught here — "Test session" returns the model server's error verbatim |

When a reply is cut, the marker says so and the full text is saved to
`replies/` next to `config.json` — nothing is lost, it just does not fit in an
email. When the agent fails or times out, the fallback reply is sent instead:
silence is the worst outcome, because the phone cannot tell it apart from a
lost message.

---

## 5b. Control mail

Some letters are not conversation. A plaintext that starts with `#clutcha:` is a
command: the bridge answers it **itself**, in seconds, without spending a model
turn or a line of context.

```
#clutcha:ping
#clutcha:config {"poll": {"intervalSeconds": 300}, "agent": {"model": "…"}}
```

`ping` returns uptime, the session's model, the polling state and the counters.
`config` applies changes and replies with what changed, line by line.

**Settable by mail:**

| Key | Range |
|---|---|
| `poll.enabled` | on / off |
| `poll.intervalSeconds` | 60–3600 |
| `poll.maxScan` | 1–200 messages per check |
| `poll.maxPerCycle` | 1–20 answers per check |
| `agent.model` | passed to `pi` verbatim; empty = `pi`'s default |
| `agent.timeoutSeconds` | 30–3600 |
| `agent.thinking` | `off`, or empty to let `pi`'s own configuration decide |
| `agent.replyMaxChars` | 500–20000 |

**Refused by mail, on purpose:** `agent.tools`, the working directory, the
session id, the system prompt, the raw command, the mailbox, the theme. Tools
decide what the model may do on this machine; that stays on the Session tab,
where a person is looking at the computer. A letter can be written by anyone holding
the key, and the key can be sitting on a phone that is not yours.

An unknown verb returns the command list. Anything without the `#clutcha:`
prefix is a message to the agent, as before.

---

## 6. Security, honestly

- **Encryption is end to end.** X25519 + HKDF + ChaCha20-Poly1305. The mail
  provider sees base64 armor and nothing else.
- **Metadata is not hidden.** Who mailed whom, when, and how large — visible.
- **The model is the other end of the pipe.** The letter is encrypted on the
  way to this computer, and then the plaintext is handed to whatever `--model`
  resolves to. A local model keeps the text on the machine; a cloud model sends
  it to that provider. Check the Session tab before assuming "at home" means
  "nowhere else".
- **The pairing code is the password.** It carries both key pairs and the
  mailbox credentials. Anyone who scans it can talk to this computer. Treat a
  screenshot of it like a password.
- **Tools are off by default.** The generated command carries `-nt`, so a
  stolen phone gets text replies. The Advanced section has one checkbox to
  drop it — then whatever your `pi` configuration allows becomes reachable,
  including `bash`. There is no approval step and no login: the mailbox is the
  only door.
- **This server listens on 127.0.0.1 only and has no login.** Anyone who can
  open the page can read `config.json`, which holds your mail token and private
  keys. Do not put it behind a tunnel; if you need remote access, use an SSH
  tunnel to your own machine.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Missing Python package(s)` | Run `install.command`, or `pip3 install --user cryptography qrcode` |
| `port 8787 is busy` | The bridge already runs (it opens a browser instead), or another app holds the port — it falls back to 8788-8796 |
| "Test connection" fails on SMTP | Port 465 is often blocked on mobile networks; try 587 with STARTTLS |
| Mail never arrives | Delivery is not instant — check again after a minute. Also check the provider's spam folder the first time |
| `mailbox busy, retrying` | A transient failure, almost always on the provider's side. It retries at 0s, 5s and 15s |
| `login: -ERR System error` / `uidl: -ERR System error` | The mailbox server refused, not a credential problem — 139's POP3 answers this for tens of seconds while it recovers. The bridge retries for about 30s, then logs the checked step so the next log line says which command failed. If it persists, open the mailbox in a browser: the account may be locked |
| App shows nothing after pairing | The letter's `{armored}` block must survive intact — preview it and compare |
| QR code does not appear | It is served as SVG, which needs nothing beyond `qrcode`. If the image still fails, the card says so — open “Show pairing code” and paste the text into the app |
| Agent answers nothing | Session tab → "Test session". A missing working directory or a bad `pi` path fails here first |
| Everything is broken | Delete `config.json`, restart, re-pair the app. Identities are regenerated |

---

## 8. Compatibility

The wire format is shared with the app and is not versioned by this project
alone. Do not change:

- armor labels `VM MESSAGE` / `VM CHARACTER` / `VM PAIRING`
- the KDF context strings `vmessager/v1/…` in `clutchabridge/crypto.py`
- the envelope layout `VM1 | ver | flags | tag(8) | id(8) | nonce(12) | …`

The SMTP headers are the one tolerant spot: replies are stamped with both
`X-Clutcha-Reply` and `X-VMessager-Reply`, and both are recognised on the way
in, so either side of the rename still works.

---

## 9. Files

```
clutcha_bridge.py        entry point, single-instance guard, opens the browser
clutchabridge/
  config.py              load / migrate (v1→v2→v3) / save 0600
  crypto.py              envelope, armor, cards, pairing code  ← wire format
  mail.py                POP3 / IMAP in, SMTP out
  template.py            the letter: language, variants, validation
  agent.py               command build/parse, cwd checks, run, session files
  service.py             the poll loop
  state.py               live log, counters, metrics.jsonl
  server.py              HTTP routes (loopback only)
  web/pages.py           Status / Setup / Session
  web/assets.py          CSS + JS, inlined — no build step, no CDN
  web/charts.py          server-rendered SVG charts
config.json              created on first run, chmod 0600, never commit
.venv/                   created by install.command
```

No build step, no bundler, no framework: Python standard library plus
`cryptography` and `qrcode`. The pairing QR is rendered as SVG (pure Python);
if Pillow happens to be installed the same endpoint serves a PNG instead.
