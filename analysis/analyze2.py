import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Deep-dive: fuzzy + statistical families, and clean-chain distributions."""
import json, sys, statistics
from collections import defaultdict, Counter

rows = [json.loads(l) for l in open(f"{ROOT}/training_corpus.jsonl")]
keys = set(json.load(open(f"{ROOT}/registry/supplier_public_keys.json"))["keys"])

def fam(r): return r["labels"].get("attack", "clean")

def atts(r): return r["chain"]["attestations"]
def by_id(r): return {a["attestation_id"]: a for a in atts(r)}

# ---- 1. All `details` strings for fuzzy families ----
for target in ("cost_anomaly", "transformation_implausible"):
    print(f"\n===== {target}: all anomaly details =====")
    for r in rows:
        if fam(r) == target:
            for a in r["labels"]["anomalies"]:
                print(" ", a["type"], "|", a["details"])

# ---- 2. t4 families: what's perturbed? perturbed node vs siblings ----
def labour_rate(a):
    c = a["costs"]; h = c.get("labour_hours", 0)
    return (c.get("labour_cost_cad", 0) / h) if h else None

print("\n\n===== t4 perturbed-node features =====")
for target in ("t4_cost_outlier", "t4_labour_outlier", "t4_origin_outlier", "t4_timing_outlier"):
    print(f"\n--- {target} ---")
    for r in rows[:99999]:
        if fam(r) != target: continue
        bid = by_id(r)
        pert = r["labels"]["t4_perturbed"]
        for pid in pert[:1]:
            a = bid.get(pid)
            if not a:
                print("   (perturbed id not in chain!)", pid); continue
            print(f"   id={pid[:14]} action={a['action_type']:20s} country={a['performed_in_country']:3s} "
                  f"mat={a['costs']['material_cad']:8.1f} lh={a['costs']['labour_hours']:5.1f} "
                  f"lc={a['costs']['labour_cost_cad']:8.1f} rate={labour_rate(a)} ts={a['timestamp']}")
        # only first 4 examples
    cnt = 0

# limit t4 print
print("\n(showing only patterns; see aggregates below)")

# ---- 3. Clean-chain distributions (for thresholds) ----
print("\n\n===== CLEAN-chain distributions =====")
mat_by_action = defaultdict(list)
labour_rate_all = []
labour_hours_by_action = defaultdict(list)
country_counts = Counter()
country_by_action = defaultdict(Counter)
mat_cost_raw = defaultdict(list)   # action -> material_cad (>0)
labour_cost_by_action = defaultdict(list)
for r in rows:
    if fam(r) != "clean": continue
    for a in atts(r):
        act = a["action_type"]
        c = a["costs"]
        country_counts[a["performed_in_country"]] += 1
        country_by_action[act][a["performed_in_country"]] += 1
        if c.get("material_cad", 0) > 0: mat_cost_raw[act].append(c["material_cad"])
        lr = labour_rate(a)
        if lr is not None and c.get("labour_hours",0) > 0:
            labour_rate_all.append(lr)
            labour_cost_by_action[act].append(c["labour_cost_cad"])
            labour_hours_by_action[act].append(c["labour_hours"])

def summ(name, xs):
    if not xs: print(f"  {name}: (none)"); return
    xs = sorted(xs)
    q = lambda p: xs[min(len(xs)-1, int(p*len(xs)))]
    print(f"  {name}: n={len(xs)} min={xs[0]:.2f} p01={q(.01):.2f} p05={q(.05):.2f} "
          f"p50={q(.5):.2f} p95={q(.95):.2f} p99={q(.99):.2f} max={xs[-1]:.2f}")

print("labour_rate (CAD/hr), all clean nodes with labour:")
summ("labour_rate", labour_rate_all)
print("\nlabour_hours by action (clean):")
for act in labour_hours_by_action: summ(act, labour_hours_by_action[act])
print("\nmaterial_cad by action (clean, >0):")
for act in mat_cost_raw: summ(act, mat_cost_raw[act])
print("\nperformed_in_country counts (clean):")
for c,n in country_counts.most_common(): print(f"   {c}: {n}")
print("\ncountry by action_type (clean):")
for act in country_by_action:
    print(f"   {act}: {dict(country_by_action[act].most_common(8))}")
