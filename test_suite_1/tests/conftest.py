from __future__ import annotations

import copy
import importlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Callable

import pytest


REPO_ROOT = Path(os.environ.get("PROVENANCE_REPO_ROOT", ".")).resolve()
if not (REPO_ROOT / "worked-example" / "recovery_drone_chain.json").exists():
    # Helpful default for this ChatGPT sandbox; harmless locally if path does not exist.
    sandbox_repo = Path("/mnt/data/provenance-hackathon-main")
    if sandbox_repo.exists():
        REPO_ROOT = sandbox_repo

sys.path.insert(0, str(REPO_ROOT))

from reference_lib.canonical import content_hash  # noqa: E402
from reference_lib.crypto import sign_attestation  # noqa: E402


def _load_json(rel: str) -> Any:
    path = REPO_ROOT / rel
    if not path.exists():
        pytest.skip(f"Missing hackathon repo file: {path}. Set PROVENANCE_REPO_ROOT.")
    return json.loads(path.read_text())


@pytest.fixture
def worked_chain() -> dict:
    return _load_json("worked-example/recovery_drone_chain.json")


@pytest.fixture
def worked_expected() -> dict:
    return _load_json("worked-example/recovery_drone_expected.json")


@pytest.fixture(scope="session")
def private_keys() -> dict[str, str]:
    data = _load_json("private_keys/supplier_private_keys.json")
    return data.get("keys", data)


def sign_with_claimed_supplier(att: dict, private_keys: dict[str, str]) -> dict:
    supplier_id = att["supplier_id"]
    assert supplier_id in private_keys, f"No private key fixture for supplier {supplier_id}"
    return sign_attestation(att, private_keys[supplier_id])


def replace_att(payload: dict, new_att: dict) -> None:
    att_id = new_att["attestation_id"]
    for i, att in enumerate(payload["attestations"]):
        if att["attestation_id"] == att_id:
            payload["attestations"][i] = new_att
            return
    raise AssertionError(f"attestation not found: {att_id}")


def get_att(payload: dict, att_id: str) -> dict:
    for att in payload["attestations"]:
        if att["attestation_id"] == att_id:
            return att
    raise AssertionError(f"attestation not found: {att_id}")


def product_att(payload: dict) -> dict:
    return get_att(payload, payload["product_attestation_id"])


def first_parent_id(att: dict) -> str:
    return att["parents"][0]["attestation_id"]


def anomaly_types(response: dict) -> set[str]:
    out = set()
    for a in response.get("anomalies", []):
        typ = a.get("type") or a.get("anomaly_type")
        if typ:
            out.add(typ)
    return out


def anomaly_ids(response: dict) -> set[str]:
    return {a.get("attestation_id") for a in response.get("anomalies", []) if a.get("attestation_id")}


def assert_has_anomaly(response: dict, expected_type: str, expected_id: str | None = None) -> None:
    matches = []
    for a in response.get("anomalies", []):
        typ = a.get("type") or a.get("anomaly_type")
        att_id = a.get("attestation_id")
        if typ == expected_type and (expected_id is None or att_id == expected_id):
            matches.append(a)
    assert matches, f"Expected anomaly type={expected_type!r} id={expected_id!r}; got {response.get('anomalies', [])!r}"


def _import_object(spec: str) -> Any:
    mod_name, obj_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    obj = mod
    for part in obj_name.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.fixture(scope="session")
def verify_payload() -> Callable[[dict], dict]:
    """Return a callable that sends a payload to the implementation under test.

    Configure with one of:
      - PROVENANCE_VERIFY_URL=http://127.0.0.1:8000/verify
      - PROVENANCE_VERIFY_FUNCTION=module:function_accepting_dict
      - PROVENANCE_APP_MODULE=app.main:app  # default fallback
    """
    url = os.environ.get("PROVENANCE_VERIFY_URL")
    if url:
        import requests

        def call_http(payload: dict) -> dict:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json()

        return call_http

    fn_spec = os.environ.get("PROVENANCE_VERIFY_FUNCTION")
    if fn_spec:
        fn = _import_object(fn_spec)

        def call_fn(payload: dict) -> dict:
            result = fn(copy.deepcopy(payload))
            assert isinstance(result, dict), "Verifier function must return a dict"
            return result

        return call_fn

    app_spec = os.environ.get("PROVENANCE_APP_MODULE", "app.main:app")
    try:
        app = _import_object(app_spec)
        from fastapi.testclient import TestClient
    except Exception as exc:
        pytest.skip(
            "No verifier target configured. Set PROVENANCE_VERIFY_URL, "
            "PROVENANCE_VERIFY_FUNCTION, or PROVENANCE_APP_MODULE. "
            f"Default app import failed: {exc}"
        )

    client = TestClient(app)

    def call_app(payload: dict) -> dict:
        resp = client.post("/verify", json=payload)
        assert resp.status_code == 200, resp.text
        return resp.json()

    return call_app


# ---------- Mutations used by pytest and Gherkin tests ----------


def mutate_signature_invalid(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["costs"]["material_cad"] += 1.23  # do not re-sign
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_unknown_supplier(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["supplier_id"] = "sup-not-in-registry"
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_parent_hash_mismatch(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    parent_id = first_parent_id(leaf)
    parent = get_att(p, parent_id)
    parent["costs"]["material_cad"] += 99.0
    parent = sign_with_claimed_supplier(parent, private_keys)  # parent signature is valid, child committed to old hash
    replace_att(p, parent)
    return p, leaf["attestation_id"]


def mutate_dangling_parent(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["parents"][0]["attestation_id"] = "att-missing-parent"
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_timestamp_inversion(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["timestamp"] = "2020-01-01T00:00:00Z"
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_unit_mismatch(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["parents"][0]["unit"] = "definitely-not-the-parent-unit"
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_mass_balance(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    parent_id = first_parent_id(leaf)
    parent = get_att(p, parent_id)

    sibling = copy.deepcopy(leaf)
    sibling["attestation_id"] = leaf["attestation_id"] + "-sibling-overconsumer"
    sibling["parents"] = [copy.deepcopy(leaf["parents"][0])]
    sibling["parents"][0]["quantity_consumed"] = float(parent["output"]["quantity_produced"])
    sibling = sign_with_claimed_supplier(sibling, private_keys)
    p["attestations"].append(sibling)
    return p, parent_id


def mutate_circular_reference(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    parent_id = first_parent_id(leaf)
    parent = get_att(p, parent_id)

    parent.setdefault("parents", []).append({
        "attestation_id": leaf["attestation_id"],
        "content_hash": content_hash(leaf),
        "quantity_consumed": 1.0,
        "unit": leaf["output"]["unit"],
    })
    parent = sign_with_claimed_supplier(parent, private_keys)
    replace_att(p, parent)
    return p, parent_id


def mutate_duplicate_replay(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    duplicated = copy.deepcopy(product_att(p))
    p["attestations"].append(duplicated)
    return p, duplicated["attestation_id"]


def mutate_final_integration_no_parents(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["parents"] = []
    leaf["action_type"] = "final_integration"
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


def mutate_negative_numeric(payload: dict, private_keys: dict[str, str]) -> tuple[dict, str]:
    p = copy.deepcopy(payload)
    leaf = product_att(p)
    leaf["costs"]["labour_cost_cad"] = -100.0
    leaf = sign_with_claimed_supplier(leaf, private_keys)
    replace_att(p, leaf)
    return p, leaf["attestation_id"]


MUTATORS = {
    "signature_invalid": mutate_signature_invalid,
    "signature_unknown_supplier": mutate_unknown_supplier,
    "parent_hash_mismatch": mutate_parent_hash_mismatch,
    "dangling_parent": mutate_dangling_parent,
    "timestamp_inversion": mutate_timestamp_inversion,
    "unit_mismatch": mutate_unit_mismatch,
    "mass_balance_violation": mutate_mass_balance,
    "circular_reference": mutate_circular_reference,
    "replay_within_chain": mutate_duplicate_replay,
    "transformation_implausible": mutate_final_integration_no_parents,
    "invalid_numeric_value": mutate_negative_numeric,
}
