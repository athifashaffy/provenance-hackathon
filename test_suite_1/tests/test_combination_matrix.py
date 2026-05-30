from __future__ import annotations

import itertools

import pytest

from conftest import anomaly_ids, anomaly_types
from factories import (
    COMPOSABLE_MUTATORS,
    accepted_types,
    apply_composable_mutations,
    selected_combination_cases,
)


def _case_id(combo: tuple[str, ...]) -> str:
    return "+".join(combo)


@pytest.mark.parametrize("mutation_names", selected_combination_cases(), ids=_case_id)
def test_combination_matrix_detects_every_injected_angle(
    verify_payload, worked_chain, private_keys, mutation_names
):
    """Multi-angle contract test.

    The default run covers every single anomaly, every pairwise combination, and
    curated triples. For a true full powerset run, use:

        FULL_COMBINATION_MATRIX=1 pytest -q tests/test_combination_matrix.py

    With 12 mutations, full mode runs 4095 cases.
    """
    payload, expected_cases = apply_composable_mutations(worked_chain, private_keys, mutation_names)

    response = verify_payload(payload)

    assert response["chain_valid"] is False
    got_types = anomaly_types(response)
    got_ids = anomaly_ids(response)

    missing = []
    for case in expected_cases:
        # Some anomaly families can be represented by equivalent semantic labels.
        if not (got_types & accepted_types(case.expected_type)):
            missing.append({
                "expected_type": case.expected_type,
                "accepted_types": sorted(accepted_types(case.expected_type)),
                "expected_id": case.expected_id,
            })
    assert not missing, {
        "mutation_names": mutation_names,
        "missing": missing,
        "got_anomalies": response.get("anomalies", []),
    }

    # At least one injected attestation ID should be represented, unless the
    # implementation reports graph-level anomalies without IDs.
    expected_ids = {c.expected_id for c in expected_cases if c.expected_id}
    assert got_ids & expected_ids or response.get("anomalies"), response


@pytest.mark.parametrize(
    "mutation_names",
    [
        ("signature_invalid", "signature_unknown_supplier"),
        ("parent_hash_mismatch", "dangling_parent"),
        ("unit_mismatch", "mass_balance_violation"),
        ("circular_reference", "timestamp_inversion"),
        ("cost_anomaly", "transformation_implausible"),
    ],
    ids=_case_id,
)
def test_mutation_order_does_not_hide_anomalies(
    verify_payload, worked_chain, private_keys, mutation_names
):
    """Same two attack angles applied forward and backward should both fail."""
    forward_payload, _ = apply_composable_mutations(worked_chain, private_keys, mutation_names)
    backward_payload, _ = apply_composable_mutations(worked_chain, private_keys, tuple(reversed(mutation_names)))

    forward = verify_payload(forward_payload)
    backward = verify_payload(backward_payload)

    assert forward["chain_valid"] is False
    assert backward["chain_valid"] is False

    forward_types = anomaly_types(forward)
    backward_types = anomaly_types(backward)

    for typ in mutation_names:
        assert forward_types & accepted_types(typ), {"direction": "forward", "typ": typ, "response": forward}
        assert backward_types & accepted_types(typ), {"direction": "backward", "typ": typ, "response": backward}


def test_full_matrix_size_is_documented():
    assert len(COMPOSABLE_MUTATORS) == 12
    assert (2 ** len(COMPOSABLE_MUTATORS)) - 1 == 4095
