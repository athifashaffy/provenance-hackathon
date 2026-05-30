"""L1 unit: mass-balance (FAQ "Mass-balance false positives / misses").

  Sum ALL consumers of a node across the whole DAG; compare to output.quantity_produced.
  Only over-consumption is a violation; under-consumption (leftover) is legal.
  Consumption must be in the parent's output.unit.
"""
from __future__ import annotations

from provtests import adapters
from provtests.builders import att, parent_ref, raw

mb = adapters.find_mass_balance_violations


def test_exact_consumption_is_clean():
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c = att(parents=[parent_ref(r, 10, unit="kg")])
    assert mb([r, c]) == []


def test_leftover_under_consumption_is_legal():
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c = att(parents=[parent_ref(r, 7, unit="kg")])  # 3kg leftover
    assert mb([r, c]) == []


def test_single_edge_over_consumption_flagged():
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c = att(parents=[parent_ref(r, 11, unit="kg")])
    assert r["attestation_id"] in mb([r, c])


def test_aggregate_over_consumption_across_multiple_children():
    # Each child legal alone (6 of 10), together 12 > 10 -> violation on parent.
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c1 = att(parents=[parent_ref(r, 6, unit="kg")])
    c2 = att(parents=[parent_ref(r, 6, unit="kg")])
    assert r["attestation_id"] in mb([r, c1, c2])


def test_aggregate_within_budget_is_clean():
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c1 = att(parents=[parent_ref(r, 5, unit="kg")])
    c2 = att(parents=[parent_ref(r, 5, unit="kg")])
    assert mb([r, c1, c2]) == []


def test_unit_mismatch_flagged():
    r = raw(material_cad=10, country="CA", unit="kg", qty=10)
    c = att(parents=[parent_ref(r, 5, unit="m2")])  # consumes in wrong unit
    assert r["attestation_id"] in mb([r, c])


def test_worked_example_has_no_mass_balance_violation(worked_example):
    chain, _ = worked_example
    assert mb(chain["attestations"]) == []
