from __future__ import annotations

import copy
import itertools
import os
from dataclasses import dataclass
from typing import Callable, Iterable

from conftest import get_att, replace_att, sign_with_claimed_supplier
from reference_lib.canonical import content_hash

MutationFn = Callable[[dict, dict[str, str]], tuple[dict, str]]


@dataclass(frozen=True)
class MutationCase:
    name: str
    expected_type: str
    expected_id: str | None
    description: str


# These IDs exist in worked-example/recovery_drone_chain.json.
# The targets are intentionally spread across different nodes so mutations compose.
RAW_FABRIC = "att-anchor-0001"
RAW_LINE = "att-anchor-0002"
RAW_INSERT = "att-anchor-0003"
RAW_SCREW_A = "att-anchor-0004"
COMP_PARACHUTE = "att-anchor-0005"
RAW_ENCLOSURE = "att-anchor-0006"
RAW_CONTROLLER = "att-anchor-0007"
RAW_GPS = "att-anchor-0008"
RAW_ORING = "att-anchor-0009"
RAW_SCREW_B = "att-anchor-0010"
RAW_CASE = "att-anchor-0011"
FINAL_DRONE = "att-anchor-0012"


def _sign(att: dict, private_keys: dict[str, str]) -> dict:
    return sign_with_claimed_supplier(att, private_keys)


def c_signature_invalid(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    att = get_att(p, RAW_FABRIC)
    att["costs"]["material_cad"] = float(att["costs"]["material_cad"]) + 17.0
    # Deliberately do not re-sign.
    replace_att(p, att)
    return p, RAW_FABRIC


def c_unknown_supplier(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    att = get_att(p, RAW_LINE)
    att["supplier_id"] = "sup-intentionally-unknown"
    # Deliberately do not re-sign; the primary expected anomaly is unknown supplier.
    replace_att(p, att)
    return p, RAW_LINE


def c_parent_hash_mismatch(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    # Modify a parent of the parachute component but keep the child's committed hash unchanged.
    parent = get_att(p, RAW_INSERT)
    parent["costs"]["material_cad"] = float(parent["costs"]["material_cad"]) + 11.0
    parent = _sign(parent, private_keys)
    replace_att(p, parent)
    return p, COMP_PARACHUTE


def c_dangling_parent(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    child = get_att(p, COMP_PARACHUTE)
    # Change a different parent slot than c_parent_hash_mismatch uses.
    child["parents"][-1]["attestation_id"] = "att-missing-parent-for-contract-test"
    child = _sign(child, private_keys)
    replace_att(p, child)
    return p, COMP_PARACHUTE


def c_timestamp_inversion(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = get_att(p, FINAL_DRONE)
    leaf["timestamp"] = "2020-01-01T00:00:00Z"
    leaf = _sign(leaf, private_keys)
    replace_att(p, leaf)
    return p, FINAL_DRONE


def c_unit_mismatch(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = get_att(p, FINAL_DRONE)
    # Use an input edge not touched by the mass-balance test.
    leaf["parents"][1]["unit"] = "wrong-test-unit"
    leaf = _sign(leaf, private_keys)
    replace_att(p, leaf)
    return p, FINAL_DRONE


def c_mass_balance(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = get_att(p, FINAL_DRONE)
    parent = get_att(p, RAW_ENCLOSURE)

    sibling = copy.deepcopy(leaf)
    sibling["attestation_id"] = "att-contract-extra-overconsumer"
    sibling["parents"] = [copy.deepcopy(next(pr for pr in leaf["parents"] if pr["attestation_id"] == RAW_ENCLOSURE))]
    sibling["parents"][0]["quantity_consumed"] = float(parent["output"]["quantity_produced"])
    sibling["timestamp"] = "2024-01-15T12:00:00Z"
    sibling = _sign(sibling, private_keys)
    p["attestations"].append(sibling)
    return p, RAW_ENCLOSURE


def c_circular_reference(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    raw = get_att(p, RAW_CONTROLLER)
    leaf = get_att(p, FINAL_DRONE)
    raw["parents"] = [{
        "attestation_id": FINAL_DRONE,
        "content_hash": content_hash(leaf),
        "quantity_consumed": 1.0,
        "unit": leaf["output"]["unit"],
    }]
    raw = _sign(raw, private_keys)
    replace_att(p, raw)
    return p, RAW_CONTROLLER


def c_duplicate_replay(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    duplicated = copy.deepcopy(get_att(p, RAW_GPS))
    p["attestations"].append(duplicated)
    return p, RAW_GPS


def c_transformation_implausible(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    att = get_att(p, RAW_ORING)
    att["action_type"] = "component_manufacture"
    att["parents"] = []
    att["costs"]["labour_hours"] = 6.0
    att = _sign(att, private_keys)
    replace_att(p, att)
    return p, RAW_ORING


def c_invalid_numeric_value(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    att = get_att(p, RAW_SCREW_B)
    att["costs"]["material_cad"] = -123.45
    att = _sign(att, private_keys)
    replace_att(p, att)
    return p, RAW_SCREW_B


def c_cost_anomaly(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    att = get_att(p, RAW_CASE)
    att["costs"]["material_cad"] = 9_999_999.0
    att = _sign(att, private_keys)
    replace_att(p, att)
    return p, RAW_CASE


COMPOSABLE_MUTATORS: dict[str, MutationFn] = {
    "signature_invalid": c_signature_invalid,
    "signature_unknown_supplier": c_unknown_supplier,
    "parent_hash_mismatch": c_parent_hash_mismatch,
    "dangling_parent": c_dangling_parent,
    "timestamp_inversion": c_timestamp_inversion,
    "unit_mismatch": c_unit_mismatch,
    "mass_balance_violation": c_mass_balance,
    "circular_reference": c_circular_reference,
    "replay_within_chain": c_duplicate_replay,
    "transformation_implausible": c_transformation_implausible,
    "invalid_numeric_value": c_invalid_numeric_value,
    "cost_anomaly": c_cost_anomaly,
}

# Some teams map malformed numbers into cost_anomaly/insufficient_data rather than a custom type.
ACCEPTED_TYPE_ALIASES: dict[str, set[str]] = {
    "invalid_numeric_value": {"invalid_numeric_value", "cost_anomaly", "insufficient_data", "bad_schema", "schema_invalid"},
    "insufficient_data": {"insufficient_data", "invalid_numeric_value", "cost_anomaly", "bad_schema", "schema_invalid"},
    "cost_anomaly": {"cost_anomaly", "t4_cost_outlier"},
    "transformation_implausible": {"transformation_implausible", "bad_schema", "schema_invalid"},
}


def accepted_types(expected_type: str) -> set[str]:
    return ACCEPTED_TYPE_ALIASES.get(expected_type, {expected_type})


def apply_composable_mutations(payload: dict, private_keys: dict[str, str], mutation_names: Iterable[str]) -> tuple[dict, list[MutationCase]]:
    current = copy.deepcopy(payload)
    cases: list[MutationCase] = []
    for name in mutation_names:
        current, expected_id = COMPOSABLE_MUTATORS[name](current, private_keys)
        cases.append(MutationCase(name=name, expected_type=name, expected_id=expected_id, description=f"applied {name}"))
    return current, cases


def selected_combination_cases() -> list[tuple[str, ...]]:
    """Return the combination set for pytest parametrization.

    Default is strong but fast: all singles, all pairs, and representative triples.
    Set FULL_COMBINATION_MATRIX=1 to run the full powerset: 2^N - 1 cases.
    Set MAX_COMBINATION_SIZE=N to cap the powerset size.
    """
    names = tuple(COMPOSABLE_MUTATORS.keys())

    if os.environ.get("FULL_COMBINATION_MATRIX") == "1":
        max_size = int(os.environ.get("MAX_COMBINATION_SIZE", str(len(names))))
        return [combo for r in range(1, max_size + 1) for combo in itertools.combinations(names, r)]

    # Default: all singles + all pairs + curated high-signal triples from different angles.
    cases: list[tuple[str, ...]] = []
    cases.extend((name,) for name in names)
    cases.extend(itertools.combinations(names, 2))
    cases.extend([
        ("signature_invalid", "parent_hash_mismatch", "mass_balance_violation"),
        ("signature_unknown_supplier", "dangling_parent", "unit_mismatch"),
        ("circular_reference", "timestamp_inversion", "replay_within_chain"),
        ("cost_anomaly", "transformation_implausible", "invalid_numeric_value"),
        ("parent_hash_mismatch", "unit_mismatch", "timestamp_inversion"),
        ("mass_balance_violation", "cost_anomaly", "signature_invalid"),
    ])
    # Preserve order, remove duplicates.
    seen = set()
    out = []
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
