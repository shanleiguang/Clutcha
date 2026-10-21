# Clutcha

Your own agent, on your own computer, reachable from your phone — through a
mailbox that cannot read the mail.

Clutcha is three parts. This repository is the middle one.

```
   Clutcha App  ──letter──▶  mailbox  ──▶  Clutcha Bridge  ──▶  pi session
    (the phone)              (dumb)       (this repository)    (your model)
                ◀──letter──           ◀──
```

| Piece | What it is | Where it comes from |
|---|---|---|
| **Clutcha App** | The phone: pairing, the conversation, the ciphertext when you want to see it. | App Store. Source not public. |
| **Clutcha Bridge** | A small web app on the computer that owns the mailbox. It opens the letters, asks the agent, seals the answer, and shows you what happened. | **This repository.** |
| **pi session** | The agent itself: a `pi` conversation on that same computer, with the model, working directory and tools you chose there. | Your `pi` install. |

The app and the bridge never talk over the network. They write each other
encrypted letters through an email mailbox that both already have, and that
mailbox only ever sees armor.

**Why a mailbox.** No port to open, no tunnel to keep alive, no server to rent,
nothing on the internet that knows Clutcha exists. The cost is latency: one round
trip is one mail delivery, usually under a minute. That is the whole trade, and
it is deliberate.

---

## Clutcha Bridge

### What it is

One Python 3 program, no build step, two dependencies (`cryptography`, `qrcode`).
It runs on the computer that holds the mailbox, serves a page on
`http://127.0.0.1:8787/`, and does one thing in a loop:

```
read the mailbox → open the letters → hand the plaintext to pi → mail the answer back
```

Everything else it does — the tabs, the pairing code, the counters — serves that
loop or tells you why it stopped.

### What you decide on it

- **Setup** — the mailbox (POP3 or IMAP in, SMTP out) and the letter template that
  carries the armor. Includes "Send a test letter to myself", so the mailbox can
  be proven before an app is involved.
- **Session** — which `pi` session the phone talks to: session id, working
  directory, model, timeout, reply limit, tools. **One way in.** The phone cannot
  change any of it.
- **Pairing** — a QR code that hands the phone its own key pair. The bridge mints
  one per device and never holds the phone's private key.
- **Status** — polls, replies, errors, latency. Monitoring, nothing else.

The bridge has no opinion about the model: `--model` is passed to `pi` exactly as
typed, local or cloud alike, and empty means "whatever `pi` defaults to". A typo
surfaces as the model server's own error, verbatim.

### What it refuses to do

- **It will not listen on anything but `127.0.0.1`.** No password, because there
  is nothing to log into: it is a page on your own computer.
- **It will not let the phone enable tools.** Tools decide what the model may do
  on that computer, and that switch stays on the Session page — where a person is
  looking at the machine. Mail cannot flip it, not even from a paired device.
- **It will not check the mailbox in the background of your attention.** Mail is
  read on the poll interval, nothing is pushed, and the phone says when it last
  looked.

---

## Requirements

| | |
|---|---|
| Computer | macOS 12+, Linux, or Windows 10+ — the bridge is plain Python, nothing below is platform-specific |
| Python | 3.9 or newer |
| Agent | [`pi`](https://github.com/badlogic/pi-mono) installed and able to answer on its own |
| Mailbox | One account that allows POP3 or IMAP plus SMTP. A dedicated address is best; the bridge's letters are only readable by the app anyway |

## Quick start

**macOS** — two double-clickable files:

```bash
git clone https://github.com/shanleiguang/Clutcha.git
cd Clutcha/bridge
./install.command      # creates .venv, installs two packages
./start.command        # opens http://127.0.0.1:8787/
```

**Linux / Windows** — the same program, started by hand:

```bash
git clone https://github.com/shanleiguang/Clutcha.git
cd Clutcha/bridge
python3 -m venv .venv
.venv/bin/pip install cryptography qrcode      # Windows: .venv\Scripts\pip
.venv/bin/python clutcha_bridge.py             # Windows: .venv\Scripts\python
```

One instance only: a second start finds the first one and opens the page instead
of failing. Ports fall back from 8787 to 8796 if something else holds it.

Then:

1. **Setup** — mailbox address and password, then "Send a test letter to myself".
2. **Session** — session id, working directory, model. "Test session" runs one
   round trip before you trust it.
3. **Setup → Pairing** — scan the QR code from the app's Remote tab.

Details, and the reasoning behind each field, are in
[`bridge/README.md`](bridge/README.md).

## What the mailbox sees

Armor, and nothing else:

```
-----BEGIN VM MESSAGE-----
Vm1B7kQ…   (base64: version, nonce, ciphertext, tag)
-----END VM MESSAGE-----
```

X25519 to agree a key, HKDF-SHA256 to derive, ChaCha20-Poly1305 to seal. The
envelope is self-describing (`VM1`), the armor labels are frozen (`VM MESSAGE`,
`VM CHARACTER`, `VM PAIRING`), and the KDF contexts are
`vmessager/v1/{salt,conv,tag}`.

What the provider still sees is metadata: a sender, a recipient, a timestamp, a
size. That is not nothing, and the README says so rather than pretending
otherwise.

## Control mail

Some letters are not conversation. A plaintext starting with `#clutcha:` is a
command, answered by the bridge itself — in seconds, without spending a model
turn:

```
#clutcha:ping                        uptime, model, working directory, poll interval
#clutcha:new                         archive the pi session; the next message starts fresh
#clutcha:config {"poll": {"intervalSeconds": 300}}
```

`config` applies polling and model settings, replies with what changed, and
refuses what mail must not touch: tools, working directory, session id, mailbox.
Anything without the prefix is a message to the agent.

## Status

The bridge works and is what this repository ships. The app is the comfortable way
to use it; without the app the bridge is still a complete implementation of the
protocol — its Setup page can send itself test letters to prove the mailbox works,
so the two halves can be brought up one at a time.

## License

MIT — see [LICENSE](LICENSE).
