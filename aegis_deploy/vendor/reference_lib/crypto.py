"""Ed25519 signing / verification for provenance attestations.

Signatures cover the canonical serialization of the attestation with the
`signature` field excluded (spec/attestation-schema.md). Ed25519 signing is
deterministic, so a fixed key + message always yields the same signature —
this is what makes the golden vectors in tests/ stable.

Keys are raw 32-byte Ed25519 keys, base64-encoded for transport.
"""
from __future__ import annotations

import base64

# `cryptography` is imported lazily (see _crypto()) so that merely importing the
# app does not load its heavy OpenSSL/Rust extension — that import was exceeding
# LiteSpeed's app-spawn timeout on the CPU-limited shared host. It loads once, on
# the first signature verification. (This module uses `from __future__ import
# annotations`, so the Ed25519* type hints below are never evaluated at runtime.)
from .canonical import canonical_serialize


def _crypto():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def generate_keypair() -> tuple[str, str]:
    """Return (private_key_b64, public_key_b64) for a fresh Ed25519 keypair."""
    _, Ed25519PrivateKey, _ = _crypto()
    priv = Ed25519PrivateKey.generate()
    return _priv_to_b64(priv), _pub_to_b64(priv.public_key())


def keypair_from_seed(seed: bytes) -> tuple[str, str]:
    """Deterministic keypair from a 32-byte seed (used for golden vectors)."""
    _, Ed25519PrivateKey, _ = _crypto()
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    return _priv_to_b64(priv), _pub_to_b64(priv.public_key())


def _priv_to_b64(priv) -> str:
    serialization, _, _ = _crypto()
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode()


def _pub_to_b64(pub) -> str:
    serialization, _, _ = _crypto()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode()


def _load_priv(b64: str):
    _, Ed25519PrivateKey, _ = _crypto()
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(b64))


def _load_pub(b64: str):
    _, _, Ed25519PublicKey = _crypto()
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(b64))


def sign_attestation(attestation: dict, private_key_b64: str) -> dict:
    """Return a copy of `attestation` with its `signature` field populated."""
    msg = canonical_serialize(attestation, exclude_signature=True)
    sig = _load_priv(private_key_b64).sign(msg)
    result = dict(attestation)
    result["signature"] = {
        "algorithm": "ed25519",
        "value": base64.b64encode(sig).decode(),
    }
    return result


def verify_attestation(attestation: dict, public_key_b64: str) -> bool:
    """True iff the signature verifies against `public_key_b64` (the key
    registered to the attestation's claimed supplier_id)."""
    sigfield = attestation.get("signature")
    if not isinstance(sigfield, dict) or "value" not in sigfield:
        return False
    if sigfield.get("algorithm") != "ed25519":
        return False
    msg = canonical_serialize(attestation, exclude_signature=True)
    try:
        _load_pub(public_key_b64).verify(base64.b64decode(sigfield["value"]), msg)
        return True
    except Exception:
        return False
