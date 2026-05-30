from __future__ import annotations

import copy
import math
import random
from typing import Callable

import pytest

pytest_bdd = pytest.importorskip("pytest_bdd")
given = pytest_bdd.given
when = pytest_bdd.when
then = pytest_bdd.then
parsers = pytest_bdd.parsers
scenarios = pytest_bdd.scenarios

from conftest import (
    MUTATORS,
    anomaly_types,
    content_hash,
    get_att,
    replace_att,
    sign_with_claimed_supplier,
)
from factories import apply_composable_mutations, accepted_types

scenarios("../features/provenance_verifier_packed.feature")


def _node_cost(att: dict) -> float:
    costs = att.get("costs", {})
    return float(costs.get("material_cad", 0) or 0) + float(costs.get("labour_cost_cad", 0) or 0)


def _resign(att: dict, private_keys: dict[str, str]) -> dict:
    return sign_with_claimed_supplier(att, private_keys)


def _set_leaf_canadian_percentage(payload: dict, private_keys: dict[str, str], target_percentage: float, last_st_country: str) -> dict:
    p = copy.deepcopy(payload)
    leaf = get_att(p, p["product_attestation_id"])
    leaf["performed_in_country"] = last_st_country
    leaf["action_type"] = "final_integration"
    leaf.setdefault("costs", {})["labour_hours"] = max(float(leaf.get("costs", {}).get("labour_hours", 0) or 0), 4.0)
    leaf["costs"]["labour_cost_cad"] = 0.0
    leaf = _resign(leaf, private_keys)
    replace_att(p, leaf)

    ca_without_leaf = 0.0
    total_without_leaf = 0.0
    for att in p["attestations"]:
        if att["attestation_id"] == leaf["attestation_id"]:
            continue
        cost = _node_cost(att)
        total_without_leaf += cost
        if att.get("performed_in_country") == "CA":
            ca_without_leaf += cost

    r = target_percentage / 100.0
    x = (r * total_without_leaf - ca_without_leaf) / (1 - r)
    if x < 0:
        pytest.skip("fixture cannot reach target percentage with non-negative leaf labour")

    leaf = get_att(p, p["product_attestation_id"])
    leaf["costs"]["labour_cost_cad"] = round(x, 6)
    leaf["performed_in_country"] = last_st_country
    leaf = _resign(leaf, private_keys)
    replace_att(p, leaf)
    return p


def _rewrite_unanchored(payload: dict, private_keys: dict[str, str]) -> dict:
    p = copy.deepcopy(payload)
    old_to_new = {att["attestation_id"]: f"unanchored-{i:04d}" for i, att in enumerate(p["attestations"], start=1)}

    for att in p["attestations"]:
        att["attestation_id"] = old_to_new[att["attestation_id"]]
        for parent_ref in att.get("parents", []):
            parent_ref["attestation_id"] = old_to_new[parent_ref["attestation_id"]]

    p["product_attestation_id"] = old_to_new[p["product_attestation_id"]]

    # After ids change, parent content hashes change. Recompute all parent refs, then sign.
    by_id = {att["attestation_id"]: att for att in p["attestations"]}
    for att in p["attestations"]:
        for parent_ref in att.get("parents", []):
            parent_ref["content_hash"] = content_hash(by_id[parent_ref["attestation_id"]])

    for i, att in enumerate(p["attestations"]):
        p["attestations"][i] = _resign(att, private_keys)
    return p


def _remove_substantial_transformations(payload: dict, private_keys: dict[str, str]) -> dict:
    p = copy.deepcopy(payload)
    for i, att in enumerate(p["attestations"]):
        if att.get("action_type") in {"component_manufacture", "subassembly", "final_integration"}:
            att.setdefault("costs", {})["labour_hours"] = 3.99
            p["attestations"][i] = _resign(att, private_keys)
    return p


def _semantic_mutators() -> dict[str, Callable[[dict, dict[str, str]], tuple[dict, str]]]:
    def mutate_att(payload: dict, private_keys: dict[str, str], att_id: str, fn: Callable[[dict], None]) -> tuple[dict, str]:
        p = copy.deepcopy(payload)
        att = get_att(p, att_id)
        fn(att)
        att = _resign(att, private_keys)
        replace_att(p, att)
        return p, att_id

    def raw_material_has_parent(payload, private_keys):
        # Attach the product as a fake parent to a raw material. This is implausible and also cyclic in many implementations.
        p = copy.deepcopy(payload)
        raw = p["attestations"][0]
        leaf = get_att(p, p["product_attestation_id"])
        raw["action_type"] = "raw_material_supply"
        raw["parents"] = [{
            "attestation_id": leaf["attestation_id"],
            "content_hash": content_hash(leaf),
            "quantity_consumed": 1.0,
            "unit": leaf["output"]["unit"],
        }]
        raw = _resign(raw, private_keys)
        replace_att(p, raw)
        return p, raw["attestation_id"]

    def component_no_parent(payload, private_keys):
        return mutate_att(payload, private_keys, p_first_raw_id(payload), lambda a: (a.update({"action_type": "component_manufacture", "parents": []}), a.setdefault("costs", {}).update({"labour_hours": 6.0})))

    def subassembly_too_few_parents(payload, private_keys):
        leaf_id = payload["product_attestation_id"]
        def fn(a):
            a["action_type"] = "subassembly"
            a["parents"] = a.get("parents", [])[:1]
            a.setdefault("costs", {})["labour_hours"] = 6.0
        return mutate_att(payload, private_keys, leaf_id, fn)

    def final_integration_no_parents(payload, private_keys):
        return MUTATORS["transformation_implausible"](payload, private_keys)

    def unknown_action_type(payload, private_keys):
        return mutate_att(payload, private_keys, payload["product_attestation_id"], lambda a: a.update({"action_type": "teleportation"}))

    def negative_material_cost(payload, private_keys):
        return mutate_att(payload, private_keys, p_first_raw_id(payload), lambda a: a.setdefault("costs", {}).update({"material_cad": -1.0}))

    def negative_labour_cost(payload, private_keys):
        return mutate_att(payload, private_keys, payload["product_attestation_id"], lambda a: a.setdefault("costs", {}).update({"labour_cost_cad": -1.0}))

    def negative_labour_hours(payload, private_keys):
        return mutate_att(payload, private_keys, payload["product_attestation_id"], lambda a: a.setdefault("costs", {}).update({"labour_hours": -1.0}))

    def negative_quantity_produced(payload, private_keys):
        return mutate_att(payload, private_keys, p_first_raw_id(payload), lambda a: a.setdefault("output", {}).update({"quantity_produced": -1.0}))

    def negative_quantity_consumed(payload, private_keys):
        leaf_id = payload["product_attestation_id"]
        def fn(a):
            a["parents"][0]["quantity_consumed"] = -1.0
        return mutate_att(payload, private_keys, leaf_id, fn)

    def labour_cost_zero_hours(payload, private_keys):
        return mutate_att(payload, private_keys, payload["product_attestation_id"], lambda a: a.setdefault("costs", {}).update({"labour_hours": 0.0, "labour_cost_cad": 500.0}))

    def high_unit_cost(payload, private_keys):
        return mutate_att(payload, private_keys, p_first_raw_id(payload), lambda a: (a.setdefault("costs", {}).update({"material_cad": 99_999_999.0}), a.setdefault("output", {}).update({"quantity_produced": 1.0})))

    def zero_total_cost(payload, private_keys):
        p = copy.deepcopy(payload)
        for i, att in enumerate(p["attestations"]):
            att.setdefault("costs", {})["material_cad"] = 0.0
            att["costs"]["labour_cost_cad"] = 0.0
            p["attestations"][i] = _resign(att, private_keys)
        return p, p["product_attestation_id"]

    return {
        "raw_material_has_parent": raw_material_has_parent,
        "component_manufacture_no_parent": component_no_parent,
        "subassembly_too_few_parents": subassembly_too_few_parents,
        "final_integration_no_parents": final_integration_no_parents,
        "unknown_action_type": unknown_action_type,
        "negative_material_cost": negative_material_cost,
        "negative_labour_cost": negative_labour_cost,
        "negative_labour_hours": negative_labour_hours,
        "negative_quantity_produced": negative_quantity_produced,
        "negative_quantity_consumed": negative_quantity_consumed,
        "labour_cost_with_zero_hours": labour_cost_zero_hours,
        "implausibly_high_unit_cost": high_unit_cost,
        "zero_total_direct_cost": zero_total_cost,
    }


def p_first_raw_id(payload: dict) -> str:
    for att in payload["attestations"]:
        if not att.get("parents"):
            return att["attestation_id"]
    return payload["attestations"][0]["attestation_id"]


@given("the worked-example recovery drone chain", target_fixture="ctx")
def given_worked_example(worked_chain):
    return {"payload": copy.deepcopy(worked_chain), "response": None}


@given("I shuffle the attestations")
def shuffle_attestations(ctx):
    random.Random(1234).shuffle(ctx["payload"]["attestations"])


@given("I rewrite every attestation id to be unanchored while preserving signatures and hash links")
def rewrite_unanchored(ctx, private_keys):
    ctx["payload"] = _rewrite_unanchored(ctx["payload"], private_keys)


@given(parsers.parse("I adjust the chain to Canadian content percentage {percentage:g} with last substantial transformation country \"{country}\""))
def adjust_canadian_percentage(ctx, percentage, country, private_keys):
    ctx["payload"] = _set_leaf_canadian_percentage(ctx["payload"], private_keys, float(percentage), country)


@given("I remove every substantial transformation from the chain")
def remove_substantial_transformations(ctx, private_keys):
    ctx["payload"] = _remove_substantial_transformations(ctx["payload"], private_keys)


@given(parsers.parse('I inject a "{mutation}" anomaly'))
def inject_anomaly(ctx, mutation, private_keys):
    assert mutation in MUTATORS, f"Unknown mutation {mutation}; options={sorted(MUTATORS)}"
    payload, expected_id = MUTATORS[mutation](ctx["payload"], private_keys)
    ctx["payload"] = payload
    ctx["expected_id"] = expected_id


@given(parsers.parse('I inject semantic anomaly "{mutation}"'))
def inject_semantic_anomaly(ctx, mutation, private_keys):
    semantic = _semantic_mutators()
    assert mutation in semantic, f"Unknown semantic mutation {mutation}; options={sorted(semantic)}"
    payload, expected_id = semantic[mutation](ctx["payload"], private_keys)
    ctx["payload"] = payload
    ctx["expected_id"] = expected_id


@given(parsers.parse('I inject anomaly combination "{mutations}"'))
def inject_anomaly_combination(ctx, mutations, private_keys):
    names = tuple(part.strip() for part in mutations.split(",") if part.strip())
    payload, expected_cases = apply_composable_mutations(ctx["payload"], private_keys, names)
    ctx["payload"] = payload
    ctx["expected_cases"] = expected_cases


@when("I verify the chain")
def verify_chain(ctx, verify_payload):
    ctx["response"] = verify_payload(ctx["payload"])


@then("the chain should be valid")
def chain_valid(ctx):
    assert ctx["response"]["chain_valid"] is True


@then("the chain should be invalid")
def chain_invalid(ctx):
    assert ctx["response"]["chain_valid"] is False


@then(parsers.parse('the designation should be "{designation}"'))
def designation_should_be(ctx, designation):
    assert ctx["response"]["designation"] == designation


@then(parsers.parse("the Canadian content percentage should be approximately {percentage:g}"))
def percentage_should_be(ctx, percentage):
    assert math.isclose(
        float(ctx["response"]["canadian_content_percentage"]),
        float(percentage),
        abs_tol=0.20,
    )


@then("no anomalies should be returned")
def no_anomalies(ctx):
    assert ctx["response"].get("anomalies", []) == []


@then(parsers.parse('the response should contain anomaly type "{anomaly_type}"'))
def response_contains_anomaly(ctx, anomaly_type):
    got = anomaly_types(ctx["response"])
    assert anomaly_type in got or bool(got & accepted_types(anomaly_type)), ctx["response"].get("anomalies", [])


@then(parsers.parse('the response should contain an accepted anomaly type for "{anomaly_type}"'))
def response_contains_accepted_anomaly(ctx, anomaly_type):
    got = anomaly_types(ctx["response"])
    assert got & accepted_types(anomaly_type), {"expected": accepted_types(anomaly_type), "got": got, "anomalies": ctx["response"].get("anomalies", [])}


@then(parsers.parse('the response should contain each anomaly type from "{mutations}"'))
def response_contains_each_anomaly_type(ctx, mutations):
    names = tuple(part.strip() for part in mutations.split(",") if part.strip())
    got = anomaly_types(ctx["response"])
    missing = [name for name in names if not (got & accepted_types(name))]
    assert not missing, {"missing": missing, "got": got, "anomalies": ctx["response"].get("anomalies", [])}


@then("the response should satisfy the verifier contract")
def response_contract(ctx):
    response = ctx["response"]
    required = {
        "product_attestation_id",
        "canadian_content_percentage",
        "designation",
        "chain_valid",
        "anomalies",
    }
    missing = required - set(response)
    assert not missing, {"missing": sorted(missing), "response": response}
    assert response["product_attestation_id"] == ctx["payload"]["product_attestation_id"]
    assert isinstance(response["canadian_content_percentage"], (int, float))
    assert response["designation"] in {"none", "made_in_canada", "product_of_canada"}
    assert isinstance(response["chain_valid"], bool)
    assert isinstance(response["anomalies"], list)


@then("every anomaly should include an attestation id and type")
def every_anomaly_has_id_and_type(ctx):
    anomalies = ctx["response"].get("anomalies", [])
    assert anomalies, "expected at least one anomaly"
    for anomaly in anomalies:
        assert anomaly.get("attestation_id"), anomaly
        assert anomaly.get("type") or anomaly.get("anomaly_type"), anomaly
