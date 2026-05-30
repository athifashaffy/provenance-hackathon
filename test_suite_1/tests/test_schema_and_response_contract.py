from __future__ import annotations

import pytest


REQUIRED_RESPONSE_KEYS = {
    "product_attestation_id",
    "canadian_content_percentage",
    "designation",
    "chain_valid",
    "anomalies",
}


@pytest.mark.parametrize("shuffle", [False, True])
def test_response_contract_shape(verify_payload, worked_chain, shuffle):
    import copy, random

    payload = copy.deepcopy(worked_chain)
    if shuffle:
        random.Random(99).shuffle(payload["attestations"])

    response = verify_payload(payload)

    assert REQUIRED_RESPONSE_KEYS <= set(response)
    assert isinstance(response["product_attestation_id"], str)
    assert isinstance(response["chain_valid"], bool)
    assert response["designation"] in {"none", "made_in_canada", "product_of_canada"}
    assert isinstance(response["anomalies"], list)
    float(response["canadian_content_percentage"])

    for anomaly in response["anomalies"]:
        assert isinstance(anomaly, dict)
        assert "attestation_id" in anomaly
        assert ("type" in anomaly) or ("anomaly_type" in anomaly)
