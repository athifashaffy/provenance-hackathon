from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import REPO_ROOT, anomaly_ids


@pytest.mark.skipif(
    os.environ.get("ENABLE_T4_CONTRACT") != "1",
    reason="Enable with ENABLE_T4_CONTRACT=1 once hard-rule tests pass.",
)
def test_first_t4_case_flags_at_least_one_expected_perturbed_id(verify_payload):
    corpus_path = REPO_ROOT / "training_corpus.jsonl"
    if not corpus_path.exists():
        pytest.skip(f"Missing {corpus_path}")

    selected = None
    expected_ids = set()
    with corpus_path.open() as f:
        for line in f:
            case = json.loads(line)
            expected = case.get("expected", {})
            anomalies = expected.get("anomalies", [])
            types = {a.get("type") or a.get("anomaly_type") for a in anomalies}
            if any(str(t).startswith("t4_") for t in types):
                selected = case
                expected_ids = {a.get("attestation_id") for a in anomalies if a.get("attestation_id")}
                break

    if selected is None:
        pytest.skip("No t4 cases found in training corpus")

    response = verify_payload(selected["request"])
    found = anomaly_ids(response)

    assert found & expected_ids, (
        "Expected the statistical detector to flag at least one labeled t4 "
        f"perturbed attestation. expected_ids={expected_ids}, found={found}, response={response}"
    )
