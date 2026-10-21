# Clutcha

An agent on your own Mac that you can reach from your phone — through a mailbox
that cannot read the mail.

Clutcha is two pieces: a small web app that runs on the Mac — the bridge, and
what this repository is — and an iOS app that talks to it. They do not talk to
each other over the network. They write each other encrypted letters through an
email mailbox that both already have, and that mailbox only ever sees armor.

```
  iOS app ──letter (VM MESSAGE armor)──▶ mailbox ──▶ bridge ──▶ pi session
  iOS app ◀──letter (VM MESSAGE armor)── mailbox ◀── bridge ◀── reply
```

**Why a mailbox.** There is no port to open, no tunnel to keep alive, no server to
rent, and nothing on the internet that knows Clutcha exists. The cost is latency:
one round trip is one mail delivery, usually under a minute. That is the whole
trade, and it is deliberate.

## What is here — and what is not

This repository holds the **bridge**: the half that runs on your Mac. Python 3,
no build step, no dependencies beyond `cryptography` and `qrcode`.

The other half is the **iOS app**, which is the client for the bridge's Remote
mode. It is distributed through the App Store and its source is not public, so
there is nothing here about it beyond what the protocol needs: the pairing
payload, the letter format, and the commands a paired phone may send.

That split is deliberate. The bridge is the part you have to trust with a mailbox
password and a `pi` session on your own machine, so it is the part you can read.

## What the bridge does

It watches one mailbox, opens the letters addressed to it, hands the plaintext to
a `pi` session on the Mac, and mails the answer back. Everything else it does
serves that loop:

- **Setup** — the mailbox (POP3 or IMAP in, SMTP out) and the letter template
  that carries the armor.
- **Session** — which `pi` session the phone talks to: session id, working
  directory, model, timeout, reply limit, tools. One way in; the phone cannot
  change these.
- **Pairing** — a QR code that hands the phone its own key pair. The bridge mints
  one per device and never holds the phone's private key.
- **Status** — polls, replies, errors, latency. Monitoring only.

The bridge never judges the model: `--model` is passed to `pi` exactly as typed,
and empty means "whatever `pi` defaults to". A typo surfaces as the model
server's own error, verbatim.

## Quick start

The app is what you pair with, but nothing below depends on it.

Requirements: macOS, Python 3.9+, [`pi`](https://github.com/badlogic/pi-mono)
installed and able to answer on its own, and a mailbox that allows POP3 or IMAP
plus SMTP.

```bash
git clone https://github.com/shanleiguang/Clutcha.git
cd Clutcha/bridge
./install.command      # creates .venv, installs two packages
./start.command        # opens http://127.0.0.1:8787/
```

Then:

1. **Setup** — mailbox address and password, then "Send a test letter to myself".
2. **Session** — session id, working directory, model. "Test session" runs one
   round trip before you trust it.
3. **Setup → Pairing** — scan the QR code from the app's Remote tab.

Details, and the reasoning behind each field, are in [`bridge/README.md`](bridge/README.md).

## What the mailbox sees

Armor, and nothing else:

```
-----BEGIN VM MESSAGE-----
Vm1B7kQ…   (base64: version, nonce, ciphertext, tag)
-----END VM MESSAGE-----
```

X25519 to agree a key, HKDF-SHA256 to derive, ChaCha20-Poly1305 to seal. The
envelope is self-describing (`VM1`), the armor labels are frozen
(`VM MESSAGE`, `VM CHARACTER`, `VM PAIRING`), and the KDF contexts are
`vmessager/v1/{salt,conv,tag}`. A mailbox provider sees a sender, a recipient, a
timestamp and a size — which is metadata, and metadata is not nothing.

## What the bridge will not do

- **It will not listen on anything but `127.0.0.1`.** There is no password
  because there is nothing to log into: it is a page on your own Mac.
- **It will not let the phone enable tools.** Tools decide what the model may do
  on this machine, and that switch stays on the Session page, where a person is
  looking at the Mac. Mail cannot flip it — not even a letter from a paired
  device.
- **It will not check the mailbox in the background of your attention.** Mail is
  read on the poll interval, replies arrive when they arrive, and the phone says
  when it last looked. Nothing is pushed.

## Control mail

Some letters are not conversation. A plaintext starting with `#clutcha:` is a
command, answered by the bridge itself — in seconds, without spending a model
turn:

```
#clutcha:ping                            uptime, model, working directory, poll interval
#clutcha:new                             archive the pi session; the next message starts fresh
#clutcha:config {"poll": {"intervalSeconds": 300}}
```

`config` applies polling and model settings and replies with what changed, and
refuses what mail must not touch (tools, working directory, session id, the
mailbox). Anything without the prefix is a message to the agent, as before.

## Status

The bridge works and is what this repository ships: install it, point it at a
mailbox and a `pi` session, and it will answer letters. The iOS app is the
comfortable way to use it; without the app the bridge is still a complete
implementation of the protocol, and its Setup page can send itself test letters
to prove the mailbox works.

## License

MIT — see [LICENSE](LICENSE).
