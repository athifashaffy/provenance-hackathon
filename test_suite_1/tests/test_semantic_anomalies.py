from __future__ import annotations

from conftest import MUTATORS, assert_has_anomaly, anomaly_ids, anomaly_types


def test_final_integration_without_parents_is_implausible(
    verify_payload, worked_chain, private_keys
):
    payload, expected_id = MUTATORS["transformation_implausible"](worked_chain, private_keys)

    response = verify_payload(payload)

    assert response["chain_valid"] is False
    assert_has_anomaly(response, "transformation_implausible", expected_id)


def test_negative_numeric_values_are_flagged(verify_payload, worked_chain, private_keys):
    payload, expected_id = MUTATORS["invalid_numeric_value"](worked_chain, private_keys)

    response = verify_payload(payload)

    assert response["chain_valid"] is False
    assert expected_id in anomaly_ids(response)
    assert anomaly_types(response) & {"invalid_numeric_value", "cost_anomaly", "insufficient_data"}
