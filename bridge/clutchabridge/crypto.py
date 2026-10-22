"""Crypto + armor + character card + pairing code.

Mirrors VMessagerCore: X25519 + HKDF + ChaCha20-Poly1305, envelope
`VM1 | ver | flags | tag(8) | msgID(8) | nonce(12) [| senderPub(32)] | ct | authTag(16)`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import config as cfg

ARMOR_BEGIN = "-----BEGIN VM MESSAGE-----"
ARMOR_END = "-----END VM MESSAGE-----"
CARD_BEGIN = "-----BEGIN VM CHARACTER-----"
CARD_END = "-----END VM CHARACTER-----"
PAIRING_BEGIN = "-----BEGIN VM PAIRING-----"
PAIRING_END = "-----END VM PAIRING-----"

CONVERSATION_KEY: bytes | None = None
CONVERSATION_TAG: bytes | None = None


def derive_conversation(assistant_private: bytes, peer_public: bytes, assistant_public: bytes):
    shared = X25519PrivateKey.from_private_bytes(assistant_private).exchange(
        X25519PublicKey.from_public_bytes(peer_public)
    )
    low, high = (assistant_public, peer_public) if assistant_public < peer_public else (peer_public, assistant_public)
    salt = hashlib.sha256(b"vmessager/v1/salt" + low + high).digest()
    conversation = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt, info=b"vmessager/v1/conv"
    ).derive(shared)
    tag_key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"\x00" * 32, info=b"vmessager/v1/tag"
    ).derive(conversation)
    return conversation, tag_key[:8]


def refresh_conversation_key() -> bool:
    global CONVERSATION_KEY, CONVERSATION_TAG
    pair = cfg.keys()
    try:
        private = bytes.fromhex(pair["assistantPrivate"])
        public = bytes.fromhex(pair["assistantPublic"])
        peer = bytes.fromhex(pair["peerPublic"])
    except Exception:
        CONVERSATION_KEY = None
        CONVERSATION_TAG = None
        return False
    try:
        CONVERSATION_KEY, CONVERSATION_TAG = derive_conversation(private, peer, public)
        return True
    except Exception:
        CONVERSATION_KEY = None
        CONVERSATION_TAG = None
        return False


refresh_conversation_key()


# --------------------------------------------------------------------------- #
# Envelope
# --------------------------------------------------------------------------- #

def open_envelope(raw: bytes) -> str | None:
    if CONVERSATION_KEY is None or CONVERSATION_TAG is None:
        return None
    if len(raw) < 33 + 16 or raw[:3] != b"VM1":
        return None
    if raw[5:13] != CONVERSATION_TAG:
        return None
    header_length = 65 if (raw[4] & 0x01) else 33
    if len(raw) < header_length + 16:
        return None
    header = raw[:header_length]
    nonce = raw[21:33]
    ciphertext, auth_tag = raw[header_length:-16], raw[-16:]
    plaintext = ChaCha20Poly1305(CONVERSATION_KEY).decrypt(nonce, ciphertext + auth_tag, header)
    return plaintext.decode("utf-8")


def parse_envelope(raw: bytes) -> dict | None:
    if len(raw) < 33 + 16 or raw[:3] != b"VM1":
        return None
    has_sender = bool(raw[4] & 0x01)
    header_length = 65 if has_sender else 33
    if len(raw) < header_length + 16:
        return None
    return {
        "flags": raw[4],
        "tag": raw[5:13],
        "sender_pub": raw[33:65] if has_sender else None,
        "header_length": header_length,
    }


def adopt_peer_key(raw: bytes, state=None) -> tuple[bytes, bytes] | None:
    """Trust-on-first-use: adopt the sender key carried by a first-contact
    envelope, but only if it reproduces the tag in that same header."""
    parsed = parse_envelope(raw)
    if parsed is None or parsed["sender_pub"] is None:
        return None
    pair = cfg.keys()
    try:
        private = bytes.fromhex(pair["assistantPrivate"])
        public = bytes.fromhex(pair["assistantPublic"])
    except Exception:
        return None
    try:
        conversation, tag = derive_conversation(private, parsed["sender_pub"], public)
    except Exception:
        return None
    if tag != parsed["tag"]:
        return None

    old = (cfg.me().get("identity") or {}).get("publicKey")
    cfg.CONFIG.setdefault("me", {}).setdefault("identity", {})["publicKey"] = parsed["sender_pub"].hex()
    cfg.save_config()
    refresh_conversation_key()
    if state is not None:
        state.add(
            "receive",
            f"adopted peer key {parsed['sender_pub'].hex()[:16]}… (was {str(old)[:16]}…)",
            "warn",
        )
    return conversation, tag


def seal_envelope(plaintext: str) -> bytes:
    if CONVERSATION_KEY is None or CONVERSATION_TAG is None:
        raise RuntimeError("bridge is not configured (no keys)")
    pair = cfg.keys()
    header = (
        b"VM1"
        + bytes([1, 0x01])
        + CONVERSATION_TAG
        + os.urandom(8)
        + os.urandom(12)
        + bytes.fromhex(pair["assistantPublic"])
    )
    nonce = header[21:33]
    return header + ChaCha20Poly1305(CONVERSATION_KEY).encrypt(nonce, plaintext.encode("utf-8"), header)


# --------------------------------------------------------------------------- #
# Armor
# --------------------------------------------------------------------------- #

def armor(data: bytes) -> str:
    return armor_with_label(data, "VM MESSAGE")


def armor_with_label(data: bytes, label: str) -> str:
    body = base64.urlsafe_b64encode(data).decode().rstrip("=")
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "\n".join([f"-----BEGIN {label}-----", *lines, f"-----END {label}-----"])


def unarmor(text: str) -> bytes | None:
    start = text.find(ARMOR_BEGIN)
    end = text.find(ARMOR_END)
    if start < 0 or end < 0:
        return None
    body = re.sub(r"\s+", "", text[start + len(ARMOR_BEGIN):end])
    body += "=" * (-len(body) % 4)
    try:
        return base64.urlsafe_b64decode(body)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Character card (VMC) and pairing code (VM PAIRING)
# --------------------------------------------------------------------------- #

def encode_character_card(name: str, public_key: bytes, email: str | None = None) -> bytes:
    out = b"VMC" + bytes([1])
    entries = [(0x01, name.encode("utf-8")), (0x02, public_key)]
    if email:
        entries.append((0x05, email.encode("utf-8")))
    for tag, value in entries:
        out += bytes([tag]) + struct.pack(">H", len(value)) + value
    return out


def decode_character_card(text: str) -> tuple[str, bytes, str | None] | None:
    start = text.find(CARD_BEGIN)
    end = text.find(CARD_END)
    if start < 0 or end < 0:
        return None
    body = re.sub(r"\s+", "", text[start + len(CARD_BEGIN):end])
    body += "=" * (-len(body) % 4)
    try:
        raw = base64.urlsafe_b64decode(body)
    except Exception:
        return None
    if len(raw) < 4 or raw[:3] != b"VMC":
        return None
    offset, name, public_key, email = 4, None, None, None
    while offset + 3 <= len(raw):
        tag = raw[offset]
        length = int.from_bytes(raw[offset + 1:offset + 3], "big")
        value = raw[offset + 3:offset + 3 + length]
        offset += 3 + length
        if tag == 0x01:
            name = value.decode("utf-8", "replace")
        elif tag == 0x02:
            public_key = value
        elif tag == 0x05:
            email = value.decode("utf-8", "replace")
    if public_key is None or len(public_key) != 32:
        return None
    return (name or "agent", public_key, email)


def generate_identity() -> tuple[bytes, bytes]:
    private = X25519PrivateKey.generate()
    raw_private = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    raw_public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return raw_private, raw_public


def agent_card(name: str, public_key: bytes, email: str | None = None) -> str:
    return armor_with_label(encode_character_card(name, public_key, email), "VM CHARACTER")


def _provisioned_mail(block: dict | None) -> dict:
    """The pairing code is the app's contract, and the app reads `password`.

    config.json calls the same secret `token`. Emitting both means a pairing
    code works no matter which name the receiving build knows.
    """
    out = dict(block or {})
    if out.get("token") and not out.get("password"):
        out["password"] = out["token"]
    return out


def build_pairing_payload() -> str | None:
    """One code with everything the app needs: the agent identity, its own
    identity and the transport settings."""
    pair = cfg.keys()
    if not pair.get("assistantPublic"):
        return None
    mail = cfg.mailbox()
    address = cfg.address()
    payload = {
        "v": 1,
        "agent": {
            "name": cfg.monkey().get("name") or "Home",
            "publicKey": pair["assistantPublic"],
            "email": address,
            "card": agent_card(cfg.monkey().get("name") or "Home", bytes.fromhex(pair["assistantPublic"]), address),
        },
        "provision": {
            "identity": {"name": cfg.me().get("name") or "Me", "privateKey": pair.get("appPrivate")},
            "email": cfg.me_mail().get("address") or address,
            "smtp": _provisioned_mail(mail.get("smtp")),
            "mailbox": _provisioned_mail(mail.get("inbox")),
        },
    }
    return armor_with_label(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "VM PAIRING")


def qr_png_bytes(text: str) -> bytes | None:
    """PNG needs Pillow (or pypng), which is not a dependency of this project.

    Kept as a preference: if the user happens to have Pillow, the QR is a PNG.
    """
    try:
        import io as _io

        import qrcode

        buffer = _io.BytesIO()
        qrcode.make(text).save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def qr_svg_bytes(text: str) -> bytes | None:
    """SVG is pure Python inside `qrcode` — no Pillow, no build step."""
    try:
        import io as _io

        import qrcode
        import qrcode.image.svg

        image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage)
        buffer = _io.BytesIO()
        image.save(buffer)
        return buffer.getvalue()
    except Exception:
        return None


def pairing_image() -> tuple[bytes, str] | None:
    """The QR as whatever the machine can actually produce.

    A stale PNG-only path returned 404 here once and the page showed a broken
    image with no explanation, so the caller gets (bytes, content type) or
    nothing — and the page decides what to say.
    """
    payload = build_pairing_payload()
    if not payload:
        return None
    png = qr_png_bytes(payload)
    if png:
        return png, "image/png"
    svg = qr_svg_bytes(payload)
    if svg:
        return svg, "image/svg+xml"
    return None


# --------------------------------------------------------------------------- #
# First-run identities
# --------------------------------------------------------------------------- #

def ensure_identities() -> bool:
    """Create both key pairs on first run so pairing works without a setup step."""
    changed = False
    monkey_identity = cfg.monkey().setdefault("identity", {})
    if not monkey_identity.get("privateKey"):
        private, public = generate_identity()
        monkey_identity["privateKey"] = private.hex()
        monkey_identity["publicKey"] = public.hex()
        changed = True
    me_identity = cfg.me().setdefault("identity", {})
    if not me_identity.get("privateKey"):
        private, public = generate_identity()
        me_identity["privateKey"] = private.hex()
        me_identity["publicKey"] = public.hex()
        changed = True
    if changed:
        cfg.save_config()
        refresh_conversation_key()
    return changed
