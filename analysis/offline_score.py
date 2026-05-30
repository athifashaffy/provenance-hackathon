import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Offline scorer: run verify_chain over the corpus with self_test's formula."""
import json, sys, os
from collections import defaultdict

from verify import verify_chain

PCT_TOL, PCT_ZERO = 0.5, 5.0

def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d

def score_case(kind, expected, t4, response):
    if kind.startswith("t4_"):
        truth = set(t4)
        flagged = {a.get("attestation_id") for a in response.get("anomalies", [])}
        tp = len(truth & flagged)
        prec = tp/len(flagged) if flagged else 0.0
        rec = tp/len(truth) if truth else 1.0
        return 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    try:
        diff = abs(float(response.get("canadian_content_percentage", -999)) - expected["canadian_content_percentage"])
    except (TypeError, ValueError):
        diff = 1e9
    pct = 1.0 if diff <= PCT_TOL else max(0.0, 1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
    desig = 1.0 if response.get("designation") == expected["designation"] else 0.0
    exp_map, resp_map = _ids_by(expected["anomalies"]), _ids_by(response.get("anomalies"))
    exp_ids, resp_ids = set(exp_map), set(resp_map)
    tp = exp_ids & resp_ids
    if not exp_ids and not resp_ids: f1 = 1.0
    elif not exp_ids or not resp_ids: f1 = 0.0
    else:
        prec, rec = len(tp)/len(resp_ids), len(tp)/len(exp_ids)
        f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    classif = (sum(1 for i in tp if exp_map[i] & resp_map[i])/len(tp)) if tp else (1.0 if not exp_ids else 0.0)
    return 0.30*pct + 0.35*f1 + 0.20*desig + 0.15*classif

rows = [json.loads(l) for l in open(f"{ROOT}/training_corpus.jsonl")]
if len(sys.argv) > 1: rows = rows[:int(sys.argv[1])]

agg = defaultdict(lambda: [0.0, 0])
total = 0.0
worst = defaultdict(list)
for row in rows:
    lab = row["labels"]; kind = lab.get("attack", "clean")
    try:
        resp = verify_chain(row["chain"])
        s = score_case(kind, lab, lab.get("t4_perturbed", []), resp)
    except Exception as e:
        s = 0.0; resp = {"err": repr(e)}
    total += s; agg[kind][0] += s; agg[kind][1] += 1
    if s < 0.8 and len(worst[kind]) < 3:
        worst[kind].append((round(s,2), row["chain"]["product_attestation_id"], lab, resp))

print(f"\noverall: {total/len(rows)*100:.1f}%  ({len(rows)} cases)\n")
print(f"{'category':28s}  avg     n")
for k in sorted(agg):
    v = agg[k]; print(f"{k:28s}  {v[0]/v[1]*100:5.1f}  {v[1]:4d}")

if "-v" in sys.argv:
    print("\n=== worst cases per category ===")
    for k in sorted(worst):
        for s, pid, lab, resp in worst[k]:
            print(f"\n[{k}] score={s} pid={pid[:14]}")
            print("  expected:", {x:lab[x] for x in ("canadian_content_percentage","designation","chain_valid")},
                  "anoms=", [(a['type'],a['attestation_id'][:10]) for a in lab['anomalies']],
                  "t4=", [t[:10] for t in lab.get('t4_perturbed',[])])
            print("  got:     ", {x:resp.get(x) for x in ("canadian_content_percentage","designation","chain_valid")},
                  "anoms=", [(a['type'],a['attestation_id'][:10]) for a in resp.get('anomalies',[])])
