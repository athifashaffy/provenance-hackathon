from __future__ import annotations

import pytest

from conftest import MUTATORS, assert_has_anomaly


@pytest.mark.parametrize(
    "expected_type",
    [
        "signature_invalid",
        "signature_unknown_supplier",
        "parent_hash_mismatch",
        "dangling_parent",
        "timestamp_inversion",
        "unit_mismatch",
        "mass_balance_violation",
        "circular_reference",
        "replay_within_chain",
    ],
)
def test_hard_rule_anomalies_make_chain_invalid(
    verify_payload, worked_chain, private_keys, expected_type
):
    payload, expected_id = MUTATORS[expected_type](worked_chain, private_keys)

    response = verify_payload(payload)

    assert response["chain_valid"] is False
    assert_has_anomaly(response, expected_type, expected_id)
