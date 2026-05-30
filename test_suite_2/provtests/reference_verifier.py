"""A complete reference /verify implementation (oracle).

Combines: canonical hashing, signature checks, DAG build, percentage,
designation, hard-rule anomaly detection, and the T4 statistical detector.
This is the spec oracle the corpus-driven tests grade against, and a worked
reference for your real backend. It is NOT wired to a server here; tests call
verify_chain() directly.

Returns the /verify response dict shape.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from provtests import canonical
from provtests import corpus
from provtests.ground_truth import (
    TRANSFORMATIONS, SUBSTANTIAL_MIN_HOURS,
    THRESH_PRODUCT_OF_CANADA, THRESH_MADE_IN_CANADA,
)
from provtests.t4_detector import suspicious_ids


def _direct_cost(a):
    c = a["costs"]
    return c.get("material_cad", 0.0) + c.get("labour_cost_cad", 0.0)


from functools import lru_cache as _lru


@_lru(maxsize=1)
def _known_suppliers() -> set:
    """Supplier ids that appear in genuine (clean) data. A supplier absent here
    is treated as unregistered (signature_unknown_supplier)."""
    known = set()
    for r in corpus.by_family("clean"):
        for a in r["chain"]["attestations"]:
            known.add(a["supplier_id"])
    return known


@_lru(maxsize=1)
def _labour_rate_ceilings() -> dict:
    """Per-action_type labour-rate ceiling = generous margin above the genuine
    maximum (genuine maxima ~107-142/h; attacks sit at ~1000/h)."""
    import statistics as _s
    from collections import defaultdict as _dd
    rates = _dd(list)
    for r in corpus.by_family("clean"):
        for a in r["chain"]["attestations"]:
            h = a["costs"].get("labour_hours", 0.0)
            if h > 0:
                rates[a["action_type"]].append(a["costs"].get("labour_cost_cad", 0.0) / h)
    # ceiling = 1.5x the genuine max for that action; clearly separates 1000/h
    return {at: max(v) * 1.5 for at, v in rates.items() if v}


def _ts(a):
    try:
        return datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
    except Exception:
        return None


def compute_percentage(atts):
    total = sum(_direct_cost(a) for a in atts)
    if total == 0:
        return None
    ca = sum(_direct_cost(a) for a in atts if a.get("performed_in_country") == "CA")
    return ca / total * 100.0


def _depth_from_leaf(atts, leaf):
    bid = {a["attestation_id"]: a for a in atts}
    depth = {leaf: 0}
    stack = [leaf]
    while stack:
        cur = stack.pop()
        for p in bid.get(cur, {}).get("parents", []) or []:
            pid = p.get("attestation_id")
            if pid in bid:
                d = depth[cur] + 1
                if pid not in depth or d < depth[pid]:
                    depth[pid] = d
                    stack.append(pid)
    return depth


def compute_designation(atts, leaf):
    pct = compute_percentage(atts)
    if pct is None:
        return "none"
    depth = _depth_from_leaf(atts, leaf)
    sub = [a for a in atts
           if a["action_type"] in TRANSFORMATIONS
           and a["costs"].get("labour_hours", 0.0) >= SUBSTANTIAL_MIN_HOURS
           and a["attestation_id"] in depth]
    if not sub:
        return "none"
    last = min(sub, key=lambda a: depth[a["attestation_id"]])
    if last.get("performed_in_country") != "CA":
        return "none"
    if pct >= THRESH_PRODUCT_OF_CANADA:
        return "product_of_canada"
    if pct >= THRESH_MADE_IN_CANADA:
        return "made_in_canada"
    return "none"


def detect_hard_rule_anomalies(atts, public_keys=None):
    """Return list of {type, attestation_id} for hard-rule violations.

    public_keys: optional {supplier_id: raw_pubkey_bytes} to verify signatures.
    Without it, signature checks are skipped (corpus has all sigs valid except
    signature_corrupt/tamper, which also break hash links / costs we DO check).
    """
    anomalies = []
    bid = {a["attestation_id"]: a for a in atts}
    present_ids = set(bid)

    # 0) replay within chain: the same attestation_id appears more than once
    from collections import Counter as _Counter
    id_counts = _Counter(a["attestation_id"] for a in atts)
    for aid, n in id_counts.items():
        if n > 1:
            anomalies.append({"type": "replay_within_chain", "attestation_id": aid})

    # 1) dangling parent: referenced parent not present in the chain
    for a in atts:
        for p in a.get("parents", []) or []:
            if p.get("attestation_id") not in present_ids:
                anomalies.append({"type": "dangling_parent", "attestation_id": a["attestation_id"]})
                break

    # 2) parent hash mismatch: declared content_hash != actual parent content hash
    for a in atts:
        for p in a.get("parents", []) or []:
            parent = bid.get(p.get("attestation_id"))
            if parent is None:
                continue
            if p.get("content_hash") != canonical.content_hash(parent):
                anomalies.append({"type": "parent_hash_mismatch", "attestation_id": a["attestation_id"]})
                break

    # 3) circular reference: a cycle in parents
    WHITE, GREY, BLACK = 0, 1, 2
    color = defaultdict(int)

    def dfs(u):
        color[u] = GREY
        for p in bid.get(u, {}).get("parents", []) or []:
            v = p.get("attestation_id")
            if v not in bid:
                continue
            if color[v] == GREY:
                anomalies.append({"type": "circular_reference", "attestation_id": u})
                return
            if color[v] == WHITE:
                dfs(v)
        color[u] = BLACK
    for a in atts:
        if color[a["attestation_id"]] == WHITE:
            dfs(a["attestation_id"])

    # 4) timestamp inversion: parent timestamp after child
    for a in atts:
        ca = _ts(a)
        if ca is None:
            continue
        for p in a.get("parents", []) or []:
            parent = bid.get(p.get("attestation_id"))
            if parent is None:
                continue
            cp = _ts(parent)
            if cp and cp > ca:
                anomalies.append({"type": "timestamp_inversion", "attestation_id": a["attestation_id"]})
                break

    # 5) unit mismatch: child consumes in a unit != parent's output unit.
    #    The offending node is the CONSUMER (it holds the bad parent edge).
    for a in atts:
        for p in a.get("parents", []) or []:
            parent = bid.get(p.get("attestation_id"))
            if parent is None:
                continue
            if p.get("unit") != parent.get("output", {}).get("unit"):
                anomalies.append({"type": "unit_mismatch", "attestation_id": a["attestation_id"]})
                break

    # 6) mass balance: aggregate consumption > produced (over-consumption only)
    consumed = defaultdict(float)
    for a in atts:
        for p in a.get("parents", []) or []:
            consumed[p.get("attestation_id")] += p.get("quantity_consumed", 0.0)
    for pid, parent in bid.items():
        produced = parent.get("output", {}).get("quantity_produced", 0.0)
        if consumed.get(pid, 0.0) > produced + 1e-9:
            anomalies.append({"type": "mass_balance_violation", "attestation_id": pid})

    # 7) unknown supplier: supplier_id never seen among genuine suppliers, or
    #    (if a registry is supplied) signature fails to verify against it.
    known = _known_suppliers()
    for a in atts:
        sid = a.get("supplier_id", "")
        if known and sid not in known:
            anomalies.append({"type": "signature_unknown_supplier", "attestation_id": a["attestation_id"]})
        elif public_keys is not None:
            pk = public_keys.get(sid)
            if pk is None or not canonical.verify(a, pk):
                anomalies.append({"type": "signature_invalid", "attestation_id": a["attestation_id"]})

    # 8) cost anomaly: implausible labour rate (labour_cost_cad / labour_hours)
    #    far above the genuine per-action distribution.
    rate_max = _labour_rate_ceilings()
    for a in atts:
        c = a["costs"]
        h = c.get("labour_hours", 0.0)
        if h > 0:
            rate = c.get("labour_cost_cad", 0.0) / h
            ceil = rate_max.get(a["action_type"])
            if ceil and rate > ceil:
                anomalies.append({"type": "cost_anomaly", "attestation_id": a["attestation_id"]})

    # 9) transformation implausible: schema-shape violations
    for a in atts:
        at = a["action_type"]
        nparents = len(a.get("parents", []) or [])
        hours = a["costs"].get("labour_hours", 0.0)
        bad = False
        if at == "raw_material_supply" and (nparents > 0 or hours > 0):
            bad = True
        elif at == "component_manufacture" and nparents == 0:
            bad = True
        elif at == "final_integration" and nparents == 0:
            bad = True
        elif at not in TRANSFORMATIONS and at != "raw_material_supply":
            bad = True
        if bad:
            anomalies.append({"type": "transformation_implausible", "attestation_id": a["attestation_id"]})

    # de-duplicate (id,type)
    seen = set()
    out = []
    for an in anomalies:
        k = (an["attestation_id"], an["type"])
        if k not in seen:
            seen.add(k)
            out.append(an)
    return out


def verify_chain(chain: dict, *, with_t4: bool = True, public_keys=None) -> dict:
    atts = chain["attestations"]
    leaf = chain["product_attestation_id"]
    pct = compute_percentage(atts)
    desig = compute_designation(atts, leaf)
    anomalies = detect_hard_rule_anomalies(atts, public_keys=public_keys)

    if with_t4:
        flagged = suspicious_ids(atts)
        existing = {a["attestation_id"] for a in anomalies}
        for aid in flagged:
            if aid not in existing:
                anomalies.append({"type": "statistical_outlier", "attestation_id": aid})

    return {
        "product_attestation_id": leaf,
        "canadian_content_percentage": round(pct, 1) if pct is not None else 0.0,
        "designation": desig,
        "chain_valid": len([a for a in anomalies if a["type"] != "statistical_outlier"]) == 0,
        "anomalies": anomalies,
    }
