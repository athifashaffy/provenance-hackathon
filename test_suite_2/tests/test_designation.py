"""L1 unit: designation (TECHNICAL_GUIDE.md §6, FAQ "designation is wrong").

Rules under test:
  substantial transformation = action_type in {component_manufacture, subassembly,
      final_integration} AND labour_hours >= 4
  last substantial transformation = qualifying node closest to the leaf
  no transformation OR last not in CA -> none
  pct >= 98 -> product_of_canada ; pct >= 51 -> made_in_canada ; else none
  thresholds inclusive.
"""
from __future__ import annotations

import pytest

from provtests import adapters
from provtests.builders import att, parent_ref, raw

desig = adapters.compute_designation


def _leaf_chain(pct_target_ca: float, last_country="CA", last_hours=6.0,
                last_action="final_integration"):
    """Build a 2-node chain hitting a target CA% with a controllable leaf."""
    foreign_cost = 100 - pct_target_ca
    r = raw(material_cad=pct_target_ca, country="CA")
    leaf = att(action_type=last_action, performed_in_country=last_country,
               labour_hours=last_hours, material_cad=0,
               labour_cost_cad=foreign_cost if last_country != "CA" else 0,
               parents=[parent_ref(r, 1)])
    # put the "foreign cost" somewhere so percentage = pct_target_ca exactly
    if last_country == "CA":
        f = att(performed_in_country="US", material_cad=foreign_cost,
                labour_cost_cad=0, action_type="raw_material_supply",
                labour_hours=0)
        return [r, leaf, f], leaf
    return [r, leaf], leaf


@pytest.mark.parametrize("p,expected", [
    (50.9, "none"),
    (51.0, "made_in_canada"),   # inclusive
    (51.1, "made_in_canada"),
    (97.9, "made_in_canada"),
    (98.0, "product_of_canada"),  # inclusive
    (100.0, "product_of_canada"),
])
def test_threshold_boundaries(p, expected):
    chain, leaf = _leaf_chain(p, last_country="CA", last_hours=6.0)
    assert desig(chain, leaf["attestation_id"]) == expected


def test_labour_hours_boundary_qualifies_at_4():
    chain, leaf = _leaf_chain(80.0, last_country="CA", last_hours=4.0)
    assert desig(chain, leaf["attestation_id"]) == "made_in_canada"


def test_labour_hours_below_4_not_substantial():
    # No qualifying transformation -> none, even at high CA%.
    chain, leaf = _leaf_chain(80.0, last_country="CA", last_hours=3.9)
    assert desig(chain, leaf["attestation_id"]) == "none"


def test_raw_material_supply_never_substantial():
    r = raw(material_cad=100, country="CA")
    leaf = att(action_type="raw_material_supply", performed_in_country="CA",
               labour_hours=50.0, material_cad=100, labour_cost_cad=0,
               parents=[])
    assert desig([leaf], leaf["attestation_id"]) == "none"


def test_high_pct_but_last_transformation_abroad_is_none():
    # 99% CA content, but final integration performed abroad -> none.
    r = raw(material_cad=99, country="CA")
    leaf = att(action_type="final_integration", performed_in_country="US",
               labour_hours=10.0, material_cad=0, labour_cost_cad=1,
               parents=[parent_ref(r, 1)])
    assert desig([r, leaf], leaf["attestation_id"]) == "none"


def test_last_transformation_is_closest_to_leaf():
    # earlier transformation in CA, final one abroad -> none (last one wins).
    r = raw(material_cad=90, country="CA")
    mid = att(action_type="component_manufacture", performed_in_country="CA",
              labour_hours=10.0, material_cad=0, labour_cost_cad=5,
              parents=[parent_ref(r, 1)])
    leaf = att(action_type="final_integration", performed_in_country="FR",
               labour_hours=10.0, material_cad=0, labour_cost_cad=5,
               parents=[parent_ref(mid, 1)])
    assert desig([r, mid, leaf], leaf["attestation_id"]) == "none"


def test_no_substantial_transformation_anywhere_is_none():
    r1 = raw(material_cad=60, country="CA")
    r2 = raw(material_cad=40, country="US")
    # leaf is assembly but only 2 labour hours -> not substantial
    leaf = att(action_type="subassembly", performed_in_country="CA",
               labour_hours=2.0, material_cad=0, labour_cost_cad=0,
               parents=[parent_ref(r1, 1), parent_ref(r2, 1)])
    assert desig([r1, r2, leaf], leaf["attestation_id"]) == "none"


def test_worked_example_designation(worked_example):
    chain, expected = worked_example
    atts = chain["attestations"]
    leaf_id = chain["product_attestation_id"]
    assert desig(atts, leaf_id) == expected["designation"]
