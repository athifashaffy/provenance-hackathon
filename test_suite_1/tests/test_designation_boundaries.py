from __future__ import annotations

import copy
import math

import pytest

from conftest import get_att, replace_att, sign_with_claimed_supplier


def _set_leaf_canadian_percentage(payload: dict, private_keys: dict[str, str], target_percentage: float, last_st_country: str = "CA") -> dict:
    """Adjust the leaf labour cost to push the whole-chain percentage near a target.

    This keeps the graph/signatures valid and specifically tests the 51%/98%
    designation thresholds plus last-substantial-transformation country rule.
    """
    p = copy.deepcopy(payload)
    leaf = get_att(p, p["product_attestation_id"])
    leaf["performed_in_country"] = last_st_country

    # Zero the existing Canadian leaf labour, compute the non-leaf totals, then
    # solve for the required Canadian leaf labour x.
    leaf["costs"]["labour_cost_cad"] = 0.0
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)

    ca_without_leaf = 0.0
    total_without_leaf = 0.0
    for att in p["attestations"]:
        costs = att.get("costs", {})
        node_cost = float(costs.get("material_cad", 0)) + float(costs.get("labour_cost_cad", 0))
        total_without_leaf += node_cost
        if att.get("performed_in_country") == "CA" and att["attestation_id"] != leaf["attestation_id"]:
            ca_without_leaf += node_cost

    r = target_percentage / 100.0
    # (ca_without_leaf + x) / (total_without_leaf + x) = r
    x = (r * total_without_leaf - ca_without_leaf) / (1 - r)
    if x < 0:
        pytest.skip("fixture cannot reach target percentage with non-negative leaf labour")

    leaf = get_att(p, p["product_attestation_id"])
    leaf["costs"]["labour_cost_cad"] = round(x, 6)
    leaf["performed_in_country"] = last_st_country
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p


@pytest.mark.parametrize(
    "target_percentage,expected_designation",
    [
        (50.90, "none"),
        (51.00, "made_in_canada"),
        (51.10, "made_in_canada"),
        (97.90, "made_in_canada"),
        (98.00, "product_of_canada"),
        (98.10, "product_of_canada"),
    ],
)
def test_designation_threshold_boundaries_ca_last_transformation(
    verify_payload, worked_chain, private_keys, target_percentage, expected_designation
):
    payload = _set_leaf_canadian_percentage(worked_chain, private_keys, target_percentage, "CA")

    response = verify_payload(payload)

    assert response["chain_valid"] is True
    assert response.get("anomalies", []) == []
    assert response["designation"] == expected_designation
    assert math.isclose(float(response["canadian_content_percentage"]), target_percentage, abs_tol=0.20)


@pytest.mark.parametrize("target_percentage", [51.0, 75.0, 98.0, 99.0])
def test_designation_requires_last_substantial_transformation_in_canada(
    verify_payload, worked_chain, private_keys, target_percentage
):
    payload = _set_leaf_canadian_percentage(worked_chain, private_keys, target_percentage, "US")

    response = verify_payload(payload)

    assert response["chain_valid"] is True
    assert response.get("anomalies", []) == []
    assert response["designation"] == "none"
