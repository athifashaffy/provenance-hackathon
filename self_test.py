"""Self-test: grade YOUR backend against the labeled training corpus.

This mirrors how the official harness scores you (same per-case formula), but runs
against training_corpus.jsonl (which ships with labels) so you can iterate locally.
The official scored set is held out and uses the same logic.

Usage:
    python3 self_test.py http://localhost:8000/verify
    python3 self_test.py http://localhost:8000/verify --limit 200

Per-case scoring:
  T4 cases (statistical):  F1 over the perturbed attestation_ids
  all others:              0.30*pct + 0.35*anomaly_F1 + 0.20*designation + 0.15*classification
"""
import argparse
import json
import os
import sys
import urllib.request

PCT_TOL, PCT_ZERO = 0.5, 5.0


def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d


def score_case(kind, expected, t4_perturbed, response):
    if kind.startswith("t4_"):
        truth = set(t4_perturbed)
        flagged = {a.get("attestation_id") for a in response.get("anomalies", [])}
        tp = len(truth & flagged)
        prec = tp / len(flagged) if flagged else 0.0
        rec = tp / len(truth) if truth else 1.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        return f1, f1
    try:
        diff = abs(float(response.get("canadian_content_percentage", -999)) - expected["canadian_content_percentage"])
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
    classif = (sum(1 for i in tp if exp_map[i] & resp_map[i]) / len(tp)) if tp else (1.0 if not exp_ids else 0.0)
    score = 0.30 * pct + 0.35 * f1 + 0.20 * desig + 0.15 * classif
    return score, f1


def call(url, sub, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(sub).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="your backend's /verify URL")
    ap.add_argument("--limit", type=int, default=0, help="grade only the first N cases")
    args = ap.parse_args()

    path = os.path.join(os.path.dirname(__file__), "training_corpus.jsonl")
    rows = [json.loads(l) for l in open(path)]
    if args.limit:
        rows = rows[:args.limit]

    from collections import defaultdict
    agg = defaultdict(lambda: [0.0, 0, 0.0])
    total = 0.0
    total_f1 = 0.0
    for row in rows:
        lab = row["labels"]
        kind = lab.get("attack", "clean")
        try:
            resp = call(args.url, row["chain"])
            s, f1 = score_case(kind, lab, lab.get("t4_perturbed", []), resp)
        except Exception as e:
            s, f1 = 0.0, 0.0
        total += s
        total_f1 += f1
        agg[kind][0] += s
        agg[kind][1] += 1
        agg[kind][2] += f1

    print(f"\noverall: {total / len(rows) * 100:.1f}%  ({len(rows)} cases)  (avg F1: {total_f1 / len(rows) * 100:.1f}%)\n")
    print(f"{'category':28s}  avg     n   f1")
    for k in sorted(agg):
        v = agg[k]
        print(f"{k:28s}  {v[0]/v[1]*100:5.1f}  {v[1]:4d}  {v[2]/v[1]*100:5.1f}")


if __name__ == "__main__":
    main()
