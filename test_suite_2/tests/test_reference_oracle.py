"""TDD: the reference oracle reproduces the corpus labels.

These lock in the *achievable* scores measured from the data so a regression in
the reference logic (or your wired-in logic via adapters) is caught immediately.
Numbers are the verified corpus measurements; floors are set just under them.
"""
from __future__ import annotations

import pytest

from provtests import corpus
from provtests import ground_truth as G
from provtests.reference_verifier import (
    compute_percentage, compute_designation, detect_hard_rule_anomalies, verify_chain,
)

pytestmark = pytest.mark.corpus


def _f1(truth, flagged):
    tp = len(truth & flagged)
    p = tp / len(flagged) if flagged else 0.0
    r = tp / len(truth) if truth else 1.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


# ---- exact reproduction on clean cases -----------------------------------

def test_percentage_exact_on_all_clean():
    for r in corpus.by_family("clean"):
        atts = corpus.attestations(r)
        got = compute_percentage(atts)
        label = r["labels"]["canadian_content_percentage"]
        if got is None:
            assert label == 0
        else:
            assert abs(got - label) <= G.PCT_TOL


def test_designation_exact_on_all_clean():
    for r in corpus.by_family("clean"):
        got = compute_designation(corpus.attestations(r), corpus.leaf_id(r))
        assert got == r["labels"]["designation"]


def test_no_false_positives_on_clean():
    """The single most important property: clean chains flag nothing."""
    for r in corpus.by_family("clean"):
        assert detect_hard_rule_anomalies(corpus.attestations(r)) == []


# ---- per-family detection floors (verified measurements) ------------------

# family -> measured anomaly-F1 with the reference detector (no Ed25519 registry)
MEASURED_F1 = {
    "timestamp_inversion": 1.00,
    "circular": 0.93,
    "transformation_implausible": 0.82,
    "unknown_supplier": 1.00,
    "cost_anomaly": 1.00,
    "mass_balance": 1.00,
    "dangling_parent": 1.00,
    "parent_hash_mismatch": 1.00,
    "unit_mismatch": 1.00,
    "replay_within_chain": 1.00,
    # registry-bounded (no public keys in this kit): documented, lower floor
    "signature_corrupt": 0.00,
    "tamper_no_resign": 0.25,
}


@pytest.mark.parametrize("family", sorted(MEASURED_F1))
def test_hard_rule_family_detection_floor(family):
    floor = MEASURED_F1[family] - 0.02
    rows = corpus.by_family(family)
    fs = [
        _f1(corpus.expected_anomaly_ids(r),
            {a["attestation_id"] for a in detect_hard_rule_anomalies(corpus.attestations(r))})
        for r in rows
    ]
    mean = sum(fs) / len(fs)
    assert mean >= floor, f"{family}: {mean:.3f} < floor {floor:.3f}"


def test_overall_self_test_floor():
    """End-to-end: the reference verifier scores ~95% via the harness formula."""
    from provtests.scoring import score_case
    total = 0.0
    rows = corpus.load()
    for r in rows:
        lab = r["labels"]
        resp = verify_chain(r["chain"])
        total += score_case(lab.get("attack", "clean"), lab, lab.get("t4_perturbed", []), resp)
    overall = total / len(rows)
    assert overall >= 0.93, f"overall {overall:.3f} below 0.93 floor"
