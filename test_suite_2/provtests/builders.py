"""Builders for synthetic attestations / chains used in edge-case tests.

Kept dependency-light: a builder produces plain dicts matching the on-wire
schema (TECHNICAL_GUIDE.md §4). Signing is optional and only used where a test
needs a genuinely valid signature (requires `cryptography`).
"""
from __future__ import annotations

import itertools
from typing import Optional

from provtests import canonical

_counter = itertools.count(1)


def att(
    *,
    aid: Optional[str] = None,
    supplier_id: str = "sup-001",
    action_type: str = "component_manufacture",
    performed_in_country: str = "CA",
    parents: Optional[list] = None,
    output_name: str = "Widget",
    quantity_produced: float = 1,
    output_unit: str = "units",
    material_cad: float = 0.0,
    labour_hours: float = 6.0,
    labour_cost_cad: float = 500.0,
    timestamp: str = "2026-04-15T14:30:00Z",
) -> dict:
    return {
        "attestation_id": aid or f"att-{next(_counter):04d}",
        "version": "1.0",
        "supplier_id": supplier_id,
        "timestamp": timestamp,
        "action_type": action_type,
        "performed_in_country": performed_in_country,
        "parents": parents or [],
        "output": {"name": output_name, "quantity_produced": quantity_produced,
                   "unit": output_unit},
        "costs": {"material_cad": material_cad, "labour_hours": labour_hours,
                  "labour_cost_cad": labour_cost_cad},
        "signature": {"algorithm": "ed25519", "value": ""},
    }


def parent_ref(parent: dict, quantity_consumed: float, unit: Optional[str] = None) -> dict:
    return {
        "attestation_id": parent["attestation_id"],
        "content_hash": canonical.content_hash(parent),
        "quantity_consumed": quantity_consumed,
        "unit": unit if unit is not None else parent["output"]["unit"],
    }


def raw(material_cad: float, country: str = "CA", unit: str = "kg", qty: float = 10,
        **kw) -> dict:
    return att(action_type="raw_material_supply", performed_in_country=country,
               material_cad=material_cad, labour_hours=0.0, labour_cost_cad=0.0,
               output_unit=unit, quantity_produced=qty, **kw)


def sign_chain(attestations: list[dict], priv_by_supplier: dict[str, bytes]) -> None:
    """Sign each attestation in place with its supplier's private key."""
    for a in attestations:
        key = priv_by_supplier.get(a["supplier_id"])
        if key is not None:
            a["signature"]["value"] = canonical.sign(a, key)


def chain_request(attestations: list[dict], leaf: dict) -> dict:
    return {"product_attestation_id": leaf["attestation_id"],
            "attestations": list(attestations)}
