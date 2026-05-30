"""L3 regression: replay training_corpus.jsonl through the harness scorer.

This is the closest mirror of the official grading. It needs both the corpus
(in the repo) and a running backend. Marked live+corpus; skips if either is
absent. It prints the same overall + per-attack-category table self_test.py does,
and asserts a configurable floor so it can gate CI.
"""
from __future__ import annotations

from collections import defaultdict

import pytest

from provtests import corpus as _corpus
from provtests.scoring import score_case

pytestmark = [pytest.mark.live, pytest.mark.corpus]

# CI floors. Start permissive; raise as the backend improves. Override via env
# if you prefer (left simple here on purpose).
MIN_OVERALL = 0.0          # set e.g. 0.70 once your core is solid
MIN_CLEAN_PRECISION = 0.0  # set e.g. 0.95 to guard against over-flagging


def _run(verify_client, rows):
    agg = defaultdict(lambda: [0.0, 0])
    total = 0.0
    clean_false_positive_cases = 0
    clean_cases = 0
    for row in rows:
        lab = row["labels"]
        kind = lab.get("attack", "clean")
        try:
            resp = verify_client(row["chain"])
            s = score_case(kind, lab, lab.get("t4_perturbed", []), resp)
            if kind == "clean":
                clean_cases += 1
                if resp.get("anomalies"):
                    clean_false_positive_cases += 1
        except Exception:
            s = 0.0
        total += s
        agg[kind][0] += s
        agg[kind][1] += 1
    return total, agg, clean_cases, clean_false_positive_cases


def test_corpus_regression(verify_client, corpus_path, corpus_limit, capsys):
    rows = list(_corpus.load(limit=corpus_limit))
    assert rows, "empty corpus"
    total, agg, clean_n, clean_fp = _run(verify_client, rows)

    overall = total / len(rows)
    lines = [f"\noverall: {overall * 100:.1f}% ({len(rows)} cases)\n",
             f"{'category':28s} avg     n"]
    for k in sorted(agg):
        v = agg[k]
        lines.append(f"{k:28s} {v[0] / v[1] * 100:5.1f}  {v[1]:4d}")
    if clean_n:
        clean_precision = 1 - clean_fp / clean_n
        lines.append(f"\nclean over-flag rate: {clean_fp}/{clean_n} "
                     f"(precision {clean_precision * 100:.1f}%)")
    report = "\n".join(lines)
    with capsys.disabled():
        print(report)

    assert overall >= MIN_OVERALL, f"overall {overall:.3f} < floor {MIN_OVERALL}"
    if clean_n and MIN_CLEAN_PRECISION:
        clean_precision = 1 - clean_fp / clean_n
        assert clean_precision >= MIN_CLEAN_PRECISION, \
            f"over-flagging clean chains: precision {clean_precision:.3f}"


def test_corpus_categories_present(corpus_path):
    """Sanity: surface the set of attack families actually in the data so you
    can see exactly what the harness exercises. Always informative, never fails."""
    rows = list(_corpus.load())
    kinds = defaultdict(int)
    anomaly_types = defaultdict(int)
    for row in rows:
        lab = row["labels"]
        kinds[lab.get("attack", "clean")] += 1
        for a in lab.get("anomalies", []) or []:
            anomaly_types[a.get("type")] += 1
    print("\nattack families:", dict(sorted(kinds.items())))
    print("anomaly types:  ", dict(sorted(anomaly_types.items())))
    assert sum(kinds.values()) == len(rows)
