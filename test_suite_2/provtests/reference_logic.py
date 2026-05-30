"""Reference implementations of the pure scoring logic, straight from the spec.

These serve two purposes:
  * a spec oracle the unit tests assert against;
  * the default target of the unit tests, until you point adapters.py at your
    own implementation.

TECHNICAL_GUIDE.md §6 + FAQ.md "Computation gotchas".
"""
from __future__ import annotations

from typing import Optional

TRANSFORMATIONS = {"component_manufacture", "subassembly", "final_integration"}


def direct_cost(att: dict) -> float:
    """material_cad + labour_cost_cad. labour_hours is NOT a cost."""
    c = att.get("costs", {})
    return float(c.get("material_cad", 0.0)) + float(c.get("labour_cost_cad", 0.0))


def compute_percentage(attestations: list[dict]) -> Optional[float]:
    """Flat sum over all attestations, attributed by performed_in_country.

    Returns None for a zero-cost chain (caller maps to insufficient_data/none).
    """
    total = sum(direct_cost(a) for a in attestations)
    if total == 0:
        return None
    ca = sum(direct_cost(a) for a in attestations if a.get("performed_in_country") == "CA")
    return ca / total * 100.0


def _is_substantial(att: dict) -> bool:
    return (att.get("action_type") in TRANSFORMATIONS
            and float(att.get("costs", {}).get("labour_hours", 0.0)) >= 4)


def _depth_from_leaf(attestations: list[dict], leaf_id: str) -> dict[str, int]:
    """Distance (in hops) from the leaf, for picking the *last* (closest) node."""
    by_id = {a["attestation_id"]: a for a in attestations}
    depth = {leaf_id: 0}
    stack = [leaf_id]
    while stack:
        cur = stack.pop()
        for p in by_id.get(cur, {}).get("parents", []) or []:
            pid = p.get("attestation_id")
            if pid in by_id:
                d = depth[cur] + 1
                if pid not in depth or d < depth[pid]:
                    depth[pid] = d
                    stack.append(pid)
    return depth


def compute_designation(attestations: list[dict], leaf_id: str) -> str:
    pct = compute_percentage(attestations)
    if pct is None:
        return "none"  # zero-cost -> insufficient_data -> none

    depth = _depth_from_leaf(attestations, leaf_id)
    substantial = [a for a in attestations
                   if _is_substantial(a) and a["attestation_id"] in depth]
    if not substantial:
        return "none"
    last = min(substantial, key=lambda a: depth[a["attestation_id"]])
    if last.get("performed_in_country") != "CA":
        return "none"

    if pct >= 98:
        return "product_of_canada"
    if pct >= 51:
        return "made_in_canada"
    return "none"


def find_mass_balance_violations(attestations: list[dict]) -> list[str]:
    """Return ids of nodes whose TOTAL consumption across the DAG exceeds output.

    Only over-consumption is a violation; leftover (under-consumption) is legal.
    Consumption must be in the parent's output.unit (mismatched units flagged too).
    """
    by_id = {a["attestation_id"]: a for a in attestations}
    consumed: dict[str, float] = {}
    unit_bad: set[str] = set()
    for child in attestations:
        for p in child.get("parents", []) or []:
            pid = p.get("attestation_id")
            parent = by_id.get(pid)
            if parent is None:
                continue
            qty = float(p.get("quantity_consumed", 0.0))
            consumed[pid] = consumed.get(pid, 0.0) + qty
            if p.get("unit") != parent.get("output", {}).get("unit"):
                unit_bad.add(pid)

    violations: list[str] = []
    EPS = 1e-9
    for pid, parent in by_id.items():
        produced = float(parent.get("output", {}).get("quantity_produced", 0.0))
        if consumed.get(pid, 0.0) > produced + EPS:
            violations.append(pid)
    return sorted(set(violations) | unit_bad)
