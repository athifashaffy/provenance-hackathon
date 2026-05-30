"""Synthetic chain builders + mutators that inject each real anomaly family.

Each mutator returns (chain_dict, injected_ids:set) so step definitions can
assert detection by exact id. Chains use the reference canonical hashing so
parent_hash links are correct unless a mutator deliberately breaks them.
"""
from __future__ import annotations

import itertools

from provtests import canonical

_c = itertools.count(1)


def _att(*, aid=None, supplier="sup-0001", action="component_manufacture",
         country="CA", parents=None, out_unit="units", produced=1,
         material=0.0, hours=6.0, labour=500.0, ts="2026-04-15T09:00:00Z"):
    return {
        "attestation_id": aid or f"att-syn-{next(_c):06d}",
        "version": "1.0", "supplier_id": supplier, "timestamp": ts,
        "action_type": action, "performed_in_country": country,
        "parents": parents or [],
        "output": {"name": "X", "quantity_produced": produced, "unit": out_unit},
        "costs": {"material_cad": material, "labour_hours": hours, "labour_cost_cad": labour},
        "signature": {"algorithm": "ed25519", "value": ""},
    }


def _pref(parent, qty, unit=None):
    return {"attestation_id": parent["attestation_id"],
            "content_hash": canonical.content_hash(parent),
            "quantity_consumed": qty,
            "unit": unit if unit is not None else parent["output"]["unit"]}


def _raw(material=100.0, country="CA", unit="kg", qty=10, **kw):
    return _att(action="raw_material_supply", country=country, material=material,
                hours=0.0, labour=0.0, out_unit=unit, produced=qty, **kw)


def _chain(atts, leaf):
    return {"product_attestation_id": leaf["attestation_id"], "attestations": atts}


def clean(country="CA", hours=6.0, pct=80.0):
    """A small clean chain at a given CA percentage with a CA final integration."""
    ca = _raw(material=pct, country="CA")
    foreign = _raw(material=100 - pct, country="US")
    leaf = _att(action="final_integration", country=country, hours=hours,
                material=0.0, labour=0.0,
                parents=[_pref(ca, 1, "kg"), _pref(foreign, 1, "kg")])
    return _chain([ca, foreign, leaf], leaf), leaf


# ---- designation helpers --------------------------------------------------

def synthetic_pct(pct, country, hours, action="final_integration"):
    ca = _raw(material=pct, country="CA")
    foreign = _raw(material=100 - pct, country="US")
    leaf = _att(action=action, country=country, hours=hours, material=0.0, labour=0.0,
                parents=[_pref(ca, 1, "kg"), _pref(foreign, 1, "kg")])
    return _chain([ca, foreign, leaf], leaf)


# ---- hard-rule mutators: return (chain, injected_ids) ---------------------

def mass_balance_over():
    r = _raw(material=100, country="CA", unit="kg", qty=10)
    c1 = _att(parents=[_pref(r, 6, "kg")])
    c2 = _att(parents=[_pref(r, 6, "kg")])
    leaf = _att(action="final_integration", hours=6, parents=[_pref(c1, 1), _pref(c2, 1)])
    return _chain([r, c1, c2, leaf], leaf), {r["attestation_id"]}


def mass_balance_leftover():
    r = _raw(material=100, country="CA", unit="kg", qty=10)
    leaf = _att(action="final_integration", hours=6, parents=[_pref(r, 4, "kg")])
    return _chain([r, leaf], leaf), set()


def unit_mismatch():
    r = _raw(material=100, country="CA", unit="kg", qty=10)
    leaf = _att(action="final_integration", hours=6, parents=[_pref(r, 5, "zz")])
    return _chain([r, leaf], leaf), {leaf["attestation_id"]}


def dangling_parent():
    leaf = _att(action="final_integration", hours=6,
                parents=[{"attestation_id": "att-ghost", "content_hash": "0" * 64,
                          "quantity_consumed": 1, "unit": "kg"}])
    return _chain([leaf], leaf), {leaf["attestation_id"]}


def parent_hash_mismatch():
    r = _raw(material=100, country="CA")
    ref = _pref(r, 1)
    r["costs"]["material_cad"] = 5  # mutate AFTER child captured the hash
    leaf = _att(action="final_integration", hours=6, parents=[ref])
    return _chain([r, leaf], leaf), {leaf["attestation_id"]}


def replay_duplicate():
    r = _raw(material=100, country="CA")
    leaf = _att(action="final_integration", hours=6, parents=[_pref(r, 1)])
    # same r appears twice
    return _chain([r, r, leaf], leaf), {r["attestation_id"]}


def timestamp_inversion():
    r = _raw(material=100, country="CA", ts="2026-04-20T09:00:00Z")
    leaf = _att(action="final_integration", hours=6, ts="2026-04-15T09:00:00Z",
                parents=[_pref(r, 1)])
    return _chain([r, leaf], leaf), {leaf["attestation_id"]}


def unknown_supplier():
    r = _raw(material=100, country="CA")
    leaf = _att(action="final_integration", hours=6, supplier="sup-ghost-9999",
                parents=[_pref(r, 1)])
    return _chain([r, leaf], leaf), {leaf["attestation_id"]}


def cost_anomaly():
    r = _raw(material=100, country="CA")
    leaf = _att(action="final_integration", hours=8.8, labour=8800.0,  # 1000/h
                parents=[_pref(r, 1)])
    return _chain([r, leaf], leaf), {leaf["attestation_id"]}


def transformation_implausible(rule):
    if rule == "raw_material_has_parent":
        p = _raw(material=50, country="CA")
        bad = _raw(material=50, country="CA", parents=[_pref(p, 1, "kg")])
        leaf = _att(action="final_integration", hours=6, parents=[_pref(bad, 1, "kg")])
        return _chain([p, bad, leaf], leaf), {bad["attestation_id"]}
    if rule == "raw_material_has_labour_hours":
        bad = _raw(material=100, country="CA")
        bad["costs"]["labour_hours"] = 9.0
        leaf = _att(action="final_integration", hours=6, parents=[_pref(bad, 1, "kg")])
        return _chain([bad, leaf], leaf), {bad["attestation_id"]}
    if rule == "component_manufacture_no_parent":
        bad = _att(action="component_manufacture", hours=6, parents=[])
        leaf = _att(action="final_integration", hours=6, parents=[_pref(bad, 1)])
        return _chain([bad, leaf], leaf), {bad["attestation_id"]}
    if rule == "final_integration_no_parent":
        bad = _att(action="final_integration", hours=6, parents=[])
        return _chain([bad], bad), {bad["attestation_id"]}
    if rule == "unknown_action_type":
        r = _raw(material=100, country="CA")
        bad = _att(action="teleportation", hours=6, parents=[_pref(r, 1, "kg")])
        return _chain([r, bad], bad), {bad["attestation_id"]}
    raise ValueError(rule)


HARD_RULE_MUTATORS = {
    "mass_balance_violation": mass_balance_over,
    "unit_mismatch": unit_mismatch,
    "dangling_parent": dangling_parent,
    "parent_hash_mismatch": parent_hash_mismatch,
    "replay_within_chain": replay_duplicate,
    "timestamp_inversion": timestamp_inversion,
    "signature_unknown_supplier": unknown_supplier,
    "cost_anomaly": cost_anomaly,
}
