"""Byte-exact canonical serialization + Ed25519 sign/verify.

Implements the rules from TECHNICAL_GUIDE.md §5 and FAQ.md:
  1. JSON, keys sorted at every level, compact (no whitespace), UTF-8.
  2. The `signature` field is excluded from the bytes that are signed/hashed.
  3. Whole numbers serialize as integers (1, not 1.0); non-whole have no
     trailing zeros (520.5, not 520.50).
  4. No NaN/Infinity.
content_hash = SHA-256 lowercase hex of the parent's canonical (sig-excluded) bytes.

This file is self-contained so the unit tests have an independent oracle even if
reference_lib is not importable. adapters.py can swap in reference_lib instead.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

try:  # optional; tests that need real signatures skip if absent
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.exceptions import InvalidSignature

    _HAVE_CRYPTO = True
except Exception:  # pragma: no cover
    _HAVE_CRYPTO = False


def _normalize_numbers(obj: Any) -> Any:
    """Whole floats -> int so they serialize as `1` not `1.0`. Reject NaN/Inf."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("NaN/Infinity not permitted in canonical form")
        if obj.is_integer():
            return int(obj)
        return obj
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_numbers(v) for v in obj]
    return obj


def canonical_bytes(attestation: dict, *, exclude_signature: bool = True) -> bytes:
    """Return the canonical byte form used for both signing and content_hash."""
    payload = {k: v for k, v in attestation.items()
               if not (exclude_signature and k == "signature")}
    payload = _normalize_numbers(payload)
    # sort_keys at every level; compact separators; ensure_ascii=False for UTF-8.
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    return text.encode("utf-8")


def content_hash(attestation: dict) -> str:
    """SHA-256 lowercase hex of the canonical, signature-excluded bytes."""
    return hashlib.sha256(canonical_bytes(attestation)).hexdigest()


# --- Ed25519 ---------------------------------------------------------------

def sign(attestation: dict, private_key_bytes: bytes) -> str:
    if not _HAVE_CRYPTO:
        raise RuntimeError("cryptography not installed")
    sk = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    import base64
    return base64.b64encode(sk.sign(canonical_bytes(attestation))).decode()


def verify(attestation: dict, public_key_bytes: bytes) -> bool:
    if not _HAVE_CRYPTO:
        raise RuntimeError("cryptography not installed")
    sig = (attestation.get("signature") or {}).get("value")
    if not sig:
        return False
    import base64
    try:
        pk = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        pk.verify(base64.b64decode(sig), canonical_bytes(attestation))
        return True
    except (InvalidSignature, Exception):
        return False
