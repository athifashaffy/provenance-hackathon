"""L1 unit: canonical serialization, content hashing, Ed25519 — the byte-exact core.

Covers TECHNICAL_GUIDE.md §5 and the FAQ "Signatures & hashing" gotchas:
 - signature field excluded before signing/hashing
 - whole numbers as int, non-whole no trailing zeros
 - keys sorted at every level, compact, UTF-8
 - content_hash = sha256 lowercase hex of canonical sig-excluded bytes
 - verify against the key registered to supplier_id, not another key
 - match the repo golden vectors
"""
from __future__ import annotations

import hashlib
import json

import pytest

from provtests import canonical
from provtests.builders import att


def test_signature_field_excluded():
    a = att()
    a["signature"]["value"] = "SHOULD_NOT_AFFECT_BYTES"
    b1 = canonical.canonical_bytes(a)
    a["signature"]["value"] = "totally_different"
    b2 = canonical.canonical_bytes(a)
    assert b1 == b2
    assert b"signature" not in b1


def test_whole_numbers_serialize_as_int():
    b = canonical.canonical_bytes({"q": 1.0, "r": 2})
    assert b == b'{"q":1,"r":2}'


def test_non_whole_no_trailing_zeros():
    b = canonical.canonical_bytes({"x": 520.50})
    assert b == b'{"x":520.5}'


def test_keys_sorted_every_level():
    b = canonical.canonical_bytes({"b": {"d": 1, "c": 2}, "a": 3})
    assert b == b'{"a":3,"b":{"c":2,"d":1}}'


def test_compact_no_whitespace():
    b = canonical.canonical_bytes({"a": [1, 2, 3]})
    assert b" " not in b and b"\n" not in b


def test_utf8_preserved():
    b = canonical.canonical_bytes({"name": "Aérospatiale"})
    assert "Aérospatiale".encode("utf-8") in b


def test_nan_infinity_rejected():
    with pytest.raises(ValueError):
        canonical.canonical_bytes({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical.canonical_bytes({"x": float("inf")})


def test_content_hash_is_lowercase_sha256_of_canonical():
    a = att()
    expected = hashlib.sha256(canonical.canonical_bytes(a)).hexdigest()
    h = canonical.content_hash(a)
    assert h == expected
    assert h == h.lower() and len(h) == 64


def test_content_hash_changes_when_parent_content_changes():
    a = att(material_cad=100.0)
    h1 = canonical.content_hash(a)
    a["costs"]["material_cad"] = 100.01
    assert canonical.content_hash(a) != h1


# --- Ed25519 round-trips (need cryptography) ------------------------------

@pytest.fixture
def keypair():
    crypto = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, pub


def test_sign_then_verify_roundtrip(keypair):
    priv, pub = keypair
    a = att()
    a["signature"]["value"] = canonical.sign(a, priv)
    assert canonical.verify(a, pub) is True


def test_verify_fails_against_wrong_key(keypair):
    priv, _pub = keypair
    crypto = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    other_pub = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    a = att()
    a["signature"]["value"] = canonical.sign(a, priv)
    assert canonical.verify(a, other_pub) is False


def test_verify_fails_when_payload_mutated(keypair):
    priv, pub = keypair
    a = att()
    a["signature"]["value"] = canonical.sign(a, priv)
    a["costs"]["material_cad"] += 1  # tamper after signing
    assert canonical.verify(a, pub) is False


# --- repo golden vectors ---------------------------------------------------

@pytest.mark.golden
def test_matches_repo_golden_vectors(repo_root):
    """If reference_lib/tests carries golden vectors as JSON we can load, our
    canonical_bytes must reproduce them. Skips gracefully otherwise."""
    candidates = list((repo_root / "reference_lib" / "tests").glob("*.json")) \
        if (repo_root / "reference_lib" / "tests").exists() else []
    vectors = []
    for p in candidates:
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and "attestation" in it and "canonical" in it:
                vectors.append(it)
    if not vectors:
        pytest.skip("no machine-readable golden vectors found; check test_golden.py")
    for v in vectors:
        got = canonical.canonical_bytes(v["attestation"])
        want = v["canonical"]
        want_b = want.encode() if isinstance(want, str) else want
        assert got == want_b
