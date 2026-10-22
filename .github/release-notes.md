The bridge on its own, zipped: unpack it anywhere, then

```bash
cd clutcha-bridge
./install.command      # macOS; on Linux/Windows see README.md
./start.command
```

macOS 12+, Linux or Windows 10+, Python 3.9+, `pi` installed and a mailbox that
allows POP3/IMAP plus SMTP. Setup needs the provider's **authorization code**, not
the login password, and POP3/SMTP have to be switched on in the mailbox first.

The pairing code on the Setup tab is what the 锦囊AI app scans. Every letter the
two exchange is sealed with X25519 + HKDF-SHA256 + ChaCha20-Poly1305; the mailbox
only ever carries armor.
