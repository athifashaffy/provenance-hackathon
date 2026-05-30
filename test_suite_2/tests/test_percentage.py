"""L1 unit: Canadian-content percentage (TECHNICAL_GUIDE.md §6, FAQ gotchas).

Routes through adapters.compute_percentage so it tests YOUR maths once wired.
"""
from __future__ import annotations

import pytest

from provtests import adapters
from provtests.builders import att, raw

pct = adapters.compute_percentage


def test_direct_cost_excludes_labour_hours():
    a = att(material_cad=100.0, labour_cost_cad=50.0, labour_hours=999.0)
    assert adapters.direct_cost(a) == 150.0  # labour_hours must not enter


def test_all_canadian_is_100():
    chain = [att(performed_in_country="CA", material_cad=0, labour_cost_cad=100)]
    assert pct(chain) == pytest.approx(100.0)


def test_all_foreign_is_0():
    chain = [att(performed_in_country="US", material_cad=0, labour_cost_cad=100)]
    assert pct(chain) == pytest.approx(0.0)


def test_attributed_by_performed_country_not_supplier():
    # Canadian supplier doing work abroad must NOT count as Canadian content.
    chain = [
        att(supplier_id="sup-CA", performed_in_country="US",
            material_cad=0, labour_cost_cad=100),
        att(supplier_id="sup-US", performed_in_country="CA",
            material_cad=0, labour_cost_cad=100),
    ]
    assert pct(chain) == pytest.approx(50.0)


def test_flat_sum_not_weighted_propagation():
    # Three equal-cost CA nodes + one equal-cost foreign node => 75%, regardless
    # of tree shape. (Flat sum, not recursive.)
    r = raw(material_cad=100, country="CA")
    m = att(performed_in_country="CA", material_cad=0, labour_cost_cad=100,
            parents=[])
    s = att(performed_in_country="CA", material_cad=0, labour_cost_cad=100)
    f = att(performed_in_country="DE", material_cad=0, labour_cost_cad=100)
    assert pct([r, m, s, f]) == pytest.approx(75.0)


def test_zero_cost_chain_returns_none_sentinel():
    chain = [att(material_cad=0, labour_cost_cad=0, labour_hours=0)]
    assert pct(chain) is None  # caller maps to insufficient_data -> none


def test_worked_example_percentage(worked_example):
    chain, expected = worked_example
    atts = chain["attestations"]
    got = pct(atts)
    assert got == pytest.approx(expected["canadian_content_percentage"], abs=0.05)


@pytest.mark.parametrize("ca,total,want", [
    (51, 100, 51.0),
    (98, 100, 98.0),
    (1, 3, 33.3333),
])
def test_ratio_examples(ca, total, want):
    chain = [
        att(performed_in_country="CA", material_cad=ca, labour_cost_cad=0),
        att(performed_in_country="US", material_cad=total - ca, labour_cost_cad=0),
    ]
    assert pct(chain) == pytest.approx(want, abs=0.01)
