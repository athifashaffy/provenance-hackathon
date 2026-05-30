"""TDD: assert the corpus has exactly the structure our suite assumes.

If the corpus ever changes, these fail first and tell you precisely what moved,
before any downstream test gives a confusing failure.
"""
from __future__ import annotations

import pytest

from provtests import corpus
from provtests import ground_truth as G

pytestmark = pytest.mark.corpus


def test_corpus_size():
    assert len(corpus.load()) == 1000


def test_family_set_matches_ground_truth():
    fams = set(corpus.group_by_family().keys())
    assert fams == G.ALL_FAMILIES


def test_family_counts():
    counts = {k: len(v) for k, v in corpus.group_by_family().items()}
    assert counts["clean"] == 705
    # attacks sum to 295
    assert sum(v for k, v in counts.items() if k != "clean") == 295


def test_anomaly_type_vocabulary_is_exactly_eleven():
    seen = set()
    for r in corpus.load():
        for a in r["labels"].get("anomalies") or []:
            seen.add(a["type"])
    assert seen == G.ANOMALY_TYPES


def test_t4_families_have_no_anomalies_and_are_valid():
    for fam in G.T4_FAMILIES:
        for r in corpus.by_family(fam):
            assert (r["labels"].get("anomalies") or []) == []
            assert r["labels"]["chain_valid"] is True
            assert r["labels"].get("t4_perturbed"), "T4 case must list perturbed ids"


def test_hard_rule_families_are_invalid_and_carry_anomalies():
    for fam in G.HARD_RULE_FAMILIES:
        for r in corpus.by_family(fam):
            assert r["labels"]["chain_valid"] is False
            assert (r["labels"].get("anomalies") or []), f"{fam} must carry anomalies"
            assert not (r["labels"].get("t4_perturbed") or [])


def test_clean_family_is_valid_with_no_flags():
    for r in corpus.by_family("clean"):
        assert r["labels"]["chain_valid"] is True
        assert (r["labels"].get("anomalies") or []) == []
        assert not (r["labels"].get("t4_perturbed") or [])


def test_designation_values_are_in_the_allowed_set():
    for r in corpus.load():
        assert r["labels"]["designation"] in G.VALID_DESIGNATIONS


def test_family_emits_expected_types():
    """Each hard-rule family emits only types within its observed set."""
    for fam, allowed in G.FAMILY_TYPES.items():
        for r in corpus.by_family(fam):
            types = {a["type"] for a in r["labels"]["anomalies"]}
            assert types <= allowed, f"{fam} emitted unexpected {types - allowed}"
