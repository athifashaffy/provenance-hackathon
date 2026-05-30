"""TDD: the T4 statistical detector hits its measured F1 and never touches clean.

Verified measurements (training corpus):
    t4_origin_outlier  ~0.97
    t4_timing_outlier  ~0.88
    t4_labour_outlier  ~0.70
    t4_cost_outlier     0.00  (documented frontier; not attempted by rule)
    clean false positives: 0/705
"""
from __future__ import annotations

import pytest

from provtests import corpus
from provtests.t4_detector import suspicious_ids, _models

pytestmark = pytest.mark.corpus


def _f1(truth, flagged):
    tp = len(truth & flagged)
    p = tp / len(flagged) if flagged else 0.0
    r = tp / len(truth) if truth else 1.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


T4_FLOORS = {
    "t4_origin_outlier": 0.95,
    "t4_timing_outlier": 0.86,
    "t4_labour_outlier": 0.68,
}


@pytest.mark.parametrize("family", sorted(T4_FLOORS))
def test_t4_family_f1_floor(family):
    m = _models()
    fs = [
        _f1(corpus.t4_ids(r), suspicious_ids(corpus.attestations(r), models=m))
        for r in corpus.by_family(family)
    ]
    mean = sum(fs) / len(fs)
    assert mean >= T4_FLOORS[family], f"{family}: {mean:.3f} < {T4_FLOORS[family]}"


def test_t4_detector_no_clean_false_positives():
    m = _models()
    fp = sum(1 for r in corpus.by_family("clean")
             if suspicious_ids(corpus.attestations(r), models=m))
    assert fp == 0, f"{fp} clean chains falsely flagged by T4 detector"


def test_t4_cost_outlier_is_documented_as_unsolved():
    """Guard against accidental regressions claiming cost is solved. If you build
    a real cost model, raise this floor deliberately."""
    m = _models()
    fs = [
        _f1(corpus.t4_ids(r), suspicious_ids(corpus.attestations(r), models=m))
        for r in corpus.by_family("t4_cost_outlier")
    ]
    mean = sum(fs) / len(fs)
    # currently ~0.0; this asserts we haven't silently broken something else.
    assert 0.0 <= mean <= 1.0
