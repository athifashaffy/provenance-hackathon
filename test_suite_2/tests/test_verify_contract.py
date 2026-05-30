"""L2 integration: the /verify HTTP contract (TECHNICAL_GUIDE.md §9, FAQ).

These hit a running backend (set BACKEND_URL, default http://localhost:8000/verify).
All marked `live`; they skip if the backend is unreachable.
"""
from __future__ import annotations

import pytest

from provtests.builders import att, parent_ref, raw, chain_request

pytestmark = pytest.mark.live

VALID_DESIGNATIONS = {"product_of_canada", "made_in_canada", "none"}


def test_response_has_required_fields(verify_client):
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    resp = verify_client(chain_request([r, leaf], leaf))
    for k in ("product_attestation_id", "canadian_content_percentage",
              "designation", "chain_valid", "anomalies"):
        assert k in resp, f"missing field {k}"


def test_designation_is_one_of_the_three(verify_client):
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    resp = verify_client(chain_request([r, leaf], leaf))
    assert resp["designation"] in VALID_DESIGNATIONS


def test_product_id_echoed(verify_client):
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    payload = chain_request([r, leaf], leaf)
    resp = verify_client(payload)
    assert resp["product_attestation_id"] == payload["product_attestation_id"]


def test_anomalies_is_list_of_typed_objects(verify_client):
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    resp = verify_client(chain_request([r, leaf], leaf))
    assert isinstance(resp["anomalies"], list)
    for a in resp["anomalies"]:
        assert "attestation_id" in a and "type" in a


def test_unordered_attestations_accepted(verify_client):
    # child before parent in the array; backend must build the DAG from parents.
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    payload = {"product_attestation_id": leaf["attestation_id"],
               "attestations": [leaf, r]}  # reversed
    resp = verify_client(payload)
    assert resp["designation"] in VALID_DESIGNATIONS


def test_malformed_input_does_not_crash(verify_client):
    # A malformed/empty chain should yield a well-formed response or a clean
    # HTTP error — never a hang. The harness scores a bad case 0 and continues.
    try:
        resp = verify_client({"product_attestation_id": "att-x", "attestations": []})
    except Exception:
        return  # clean HTTP error is acceptable
    assert isinstance(resp, dict)


def test_worked_example_end_to_end(verify_client, worked_example):
    chain, expected = worked_example
    resp = verify_client(chain)
    assert resp["designation"] == expected["designation"]
    assert abs(resp["canadian_content_percentage"]
               - expected["canadian_content_percentage"]) <= 0.5
    assert resp["chain_valid"] == expected["chain_valid"]


@pytest.mark.slow
def test_throughput_many_sequential_calls(verify_client):
    # FAQ: harness sends hundreds of chains; keep /verify fast and stateless.
    import time
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="CA",
               labour_hours=6, parents=[parent_ref(r, 1)])
    payload = chain_request([r, leaf], leaf)
    t0 = time.time()
    n = 50
    for _ in range(n):
        verify_client(payload)
    per = (time.time() - t0) / n
    assert per < 1.0, f"too slow: {per:.3f}s/call (avoid per-request key/model reload)"
