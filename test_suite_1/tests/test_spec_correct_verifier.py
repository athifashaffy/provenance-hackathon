from __future__ import annotations

import copy
import math
import random

from conftest import anomaly_types


def test_worked_example_clean_chain_matches_expected(verify_payload, worked_chain, worked_expected):
    response = verify_payload(worked_chain)

    assert response["product_attestation_id"] == worked_expected["product_attestation_id"]
    assert response["chain_valid"] is True
    assert response.get("anomalies", []) == []
    assert response["designation"] == worked_expected["designation"]
    assert math.isclose(
        float(response["canadian_content_percentage"]),
        float(worked_expected["canadian_content_percentage"]),
        abs_tol=0.15,
    )


def test_attestations_are_unordered(verify_payload, worked_chain, worked_expected):
    payload = copy.deepcopy(worked_chain)
    random.Random(1234).shuffle(payload["attestations"])

    response = verify_payload(payload)

    assert response["chain_valid"] is True
    assert response.get("anomalies", []) == []
    assert response["designation"] == worked_expected["designation"]
    assert math.isclose(
        float(response["canadian_content_percentage"]),
        float(worked_expected["canadian_content_percentage"]),
        abs_tol=0.15,
    )


def test_clean_chain_does_not_flag_statistical_or_semantic_noise(verify_payload, worked_chain):
    response = verify_payload(worked_chain)
    assert response["chain_valid"] is True
    assert not anomaly_types(response)
