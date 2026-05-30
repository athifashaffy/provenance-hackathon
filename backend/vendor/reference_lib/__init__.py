"""Reference library for the Cryptographic Provenance challenge.

Shared, byte-exact core used by the organizer generator + scoring harness and
shipped to teams. The canonical serialization here is the source of truth for
signatures and content hashes.
"""
from .canonical import canonical_serialize, content_hash
from .crypto import (
    generate_keypair,
    keypair_from_seed,
    sign_attestation,
    verify_attestation,
)

__all__ = [
    "canonical_serialize",
    "content_hash",
    "generate_keypair",
    "keypair_from_seed",
    "sign_attestation",
    "verify_attestation",
]
