"""The official per-case scoring formula, lifted verbatim from self_test.py.

Kept separate so the corpus regression test scores identically to the harness.
T4 (statistical) cases: F1 over the perturbed attestation_ids.
All others: 0.30*pct + 0.35*anomaly_F1 + 0.20*designation + 0.15*classification.
"""
from __future__ import annotations

PCT_TOL, PCT_ZERO = 0.5, 5.0


def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d


def score_case(kind: str, expected: dict, t4_perturbed: list, response: dict) -> float:
    if kind.startswith("t4_"):
        truth = set(t4_perturbed)
        flagged = {a.get("attestation_id") for a in response.get("anomalies", [])}
        tp = len(truth & flagged)
        prec = tp / len(flagged) if flagged else 0.0
        rec = tp / len(truth) if truth else 1.0
        return 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    try:
        diff = abs(float(response.get("canadian_content_percentage", -999))
                   - expected["canadian_content_percentage"])
    except (TypeError, ValueError):
        diff = 1e9
    pct = 1.0 if diff <= PCT_TOL else max(0.0, 1 - (diff - PCT_TOL) / (PCT_ZERO - PCT_TOL))

    desig = 1.0 if response.get("designation") == expected["designation"] else 0.0

    exp_map, resp_map = _ids_by(expected["anomalies"]), _ids_by(response.get("anomalies"))
    exp_ids, resp_ids = set(exp_map), set(resp_map)
    tp = exp_ids & resp_ids
    if not exp_ids and not resp_ids:
        f1 = 1.0
    elif not exp_ids or not resp_ids:
        f1 = 0.0
    else:
        prec, rec = len(tp) / len(resp_ids), len(tp) / len(exp_ids)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    classif = (sum(1 for i in tp if exp_map[i] & resp_map[i]) / len(tp)) if tp \
        else (1.0 if not exp_ids else 0.0)

    return 0.30 * pct + 0.35 * f1 + 0.20 * desig + 0.15 * classif
