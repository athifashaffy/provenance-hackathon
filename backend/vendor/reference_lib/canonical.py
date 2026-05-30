"""Canonical serialization for provenance attestations.

Implements the byte-exact rules from spec/attestation-schema.md so that
signatures and content hashes match across independent implementations.

Rules:
  1. JSON, keys sorted alphabetically (by Unicode code point) at every level.
  2. No insignificant whitespace (compact separators ',' and ':').
  3. UTF-8 encoding; printable non-ASCII emitted as raw UTF-8 (NOT \\uXXXX).
     Only control chars (< 0x20) and the JSON-required chars are escaped.
  4. The `signature` field is excluded from the bytes-to-sign / content hash.
  5. Whole numbers serialize as integers (1, not 1.0); non-whole as floats
     with no trailing zeros (520.5, not 520.50).
  6. No NaN / Infinity / scientific notation.

All attestation keys in this challenge are ASCII, so code-point key ordering
is unambiguous. Reimplementations in other languages must match these rules
byte-for-byte (see the golden vectors in tests/).
"""
from __future__ import annotations

import hashlib
import math
from typing import Any


def _format_number(n: Any) -> str:
    # bool is a subclass of int — must be checked first
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float):
        if not math.isfinite(n):
            raise ValueError(f"non-finite number not allowed in canonical form: {n!r}")
        if n == int(n):
            return str(int(n))  # whole float -> integer form (1.0 -> "1")
        s = repr(n)  # CPython repr is the shortest round-trippable decimal
        if "e" in s or "E" in s:
            raise ValueError(f"scientific notation not supported in canonical form: {s}")
        return s
    raise TypeError(f"unsupported number type: {type(n)}")


def _escape_string(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)  # printable ASCII and raw UTF-8 pass through
    out.append('"')
    return "".join(out)


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _format_number(value)
    if isinstance(value, str):
        return _escape_string(value)
    if isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise TypeError(f"object keys must be strings, got {type(k)}")
        items = sorted(value.items(), key=lambda kv: kv[0])
        return "{" + ",".join(_escape_string(k) + ":" + _serialize(v) for k, v in items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_serialize(v) for v in value) + "]"
    raise TypeError(f"unsupported type in canonical form: {type(value)}")


def canonical_serialize(obj: Any, *, exclude_signature: bool = False) -> bytes:
    """Return the canonical UTF-8 byte serialization of `obj`.

    When `exclude_signature` is True and `obj` is a dict, the top-level
    `signature` field is dropped (used for both signing and hashing).
    """
    if exclude_signature and isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k != "signature"}
    return _serialize(obj).encode("utf-8")


def content_hash(attestation: dict) -> str:
    """SHA-256 (lowercase hex) over the canonical form, signature excluded.

    This is the value used for parents[].content_hash and the anchor registry.
    """
    return hashlib.sha256(
        canonical_serialize(attestation, exclude_signature=True)
    ).hexdigest()
