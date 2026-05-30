import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Verify timing + origin hypotheses; gather thresholds for labour/cost."""
import json, sys
from collections import defaultdict, Counter

rows = [json.loads(l) for l in open(f"{ROOT}/training_corpus.jsonl")]
def fam(r): return r["labels"].get("attack", "clean")
def atts(r): return r["chain"]["attestations"]

# ---- 1. CLEAN time-of-day distribution by action_type ----
print("===== CLEAN time-of-day by action_type =====")
tod = defaultdict(Counter)
for r in rows:
    if fam(r) != "clean": continue
    for a in atts(r):
        t = a["timestamp"].split("T")[1]
        tod[a["action_type"]][t] += 1
for act, c in tod.items():
    print(f"  {act}: {dict(c.most_common(5))}  (distinct={len(c)})")

# ---- 2. Does timing-outlier deviate from canonical times? ----
print("\n===== t4_timing: perturbed time-of-day vs canonical =====")
CANON = {"raw_material_supply": "09:00:00Z"}
TRANSFORM_CANON = "14:30:00Z"
hits = 0; tot = 0
for r in rows:
    if fam(r) != "t4_timing_outlier": continue
    bid = {a["attestation_id"]: a for a in atts(r)}
    for pid in r["labels"]["t4_perturbed"]:
        a = bid.get(pid);
        if not a: continue
        tot += 1
        t = a["timestamp"].split("T")[1]
        canon = CANON.get(a["action_type"], TRANSFORM_CANON)
        if t != canon: hits += 1
print(f"  perturbed nodes with NON-canonical time: {hits}/{tot}")

# count clean nodes that would be FALSELY flagged by 'non-canonical time'
false_clean = 0; clean_nodes = 0
for r in rows:
    if fam(r) != "clean": continue
    for a in atts(r):
        clean_nodes += 1
        t = a["timestamp"].split("T")[1]
        canon = CANON.get(a["action_type"], TRANSFORM_CANON)
        if t != canon: false_clean += 1
print(f"  clean nodes with non-canonical time (false positives): {false_clean}/{clean_nodes}")

# ---- 3. Origin outlier: supplier_id and output.name normal country in clean ----
print("\n===== ORIGIN: clean country-mode by supplier_id and output.name =====")
sup_country = defaultdict(Counter)
name_country = defaultdict(Counter)
for r in rows:
    if fam(r) != "clean": continue
    for a in atts(r):
        if a["action_type"] != "raw_material_supply": continue
        sup_country[a["supplier_id"]][a["performed_in_country"]] += 1
        name_country[a["output"]["name"]][a["performed_in_country"]] += 1

print("  example perturbed origin nodes — is their (supplier/name) normally foreign?")
checked=0
for r in rows:
    if fam(r) != "t4_origin_outlier": continue
    bid = {a["attestation_id"]: a for a in atts(r)}
    for pid in r["labels"]["t4_perturbed"]:
        a = bid.get(pid)
        if not a: continue
        sid=a["supplier_id"]; nm=a["output"]["name"]; ctry=a["performed_in_country"]
        sc = sup_country.get(sid); nc = name_country.get(nm)
        print(f"   {pid[:12]} ctry={ctry} sup={sid} supModeClean={dict(sc.most_common(3)) if sc else None} "
              f"nameModeClean={dict(nc.most_common(3)) if nc else None}")
        checked+=1
    if checked>=12: break

# ---- 4. labour_hours & rate thresholds per action (clean p99) vs t4 ----
print("\n===== labour_hours per action: clean p99/max vs t4_labour perturbed =====")
lh = defaultdict(list); rate=defaultdict(list)
for r in rows:
    if fam(r) != "clean": continue
    for a in atts(r):
        c=a["costs"]; h=c.get("labour_hours",0)
        if h>0:
            lh[a["action_type"]].append(h)
            rate[a["action_type"]].append(c["labour_cost_cad"]/h)
import statistics
for act in lh:
    xs=sorted(lh[act]); rs=sorted(rate[act])
    p=lambda L,q:L[min(len(L)-1,int(q*len(L)))]
    print(f"  {act}: hours p95={p(xs,.95):.1f} p99={p(xs,.99):.1f} max={xs[-1]:.1f} | "
          f"rate p95={p(rs,.95):.1f} p99={p(rs,.99):.1f} max={rs[-1]:.1f}")

# ---- 5. how many t4 cases have >1 perturbed id? and is perturbed always present in chain? ----
multi=0; missing=0; total=0
for r in rows:
    if not fam(r).startswith("t4_"): continue
    total+=1
    ids={a["attestation_id"] for a in atts(r)}
    p=r["labels"]["t4_perturbed"]
    if len(p)>1: multi+=1
    if any(x not in ids for x in p): missing+=1
print(f"\nt4 cases: {total}, with >1 perturbed: {multi}, with perturbed-id-not-in-chain: {missing}")

# ---- 6. Do hard-anomaly (non-t4, non-clean) cases ever set t4_perturbed? ----
hard_with_t4=0
for r in rows:
    f=fam(r)
    if f=="clean" or f.startswith("t4_"): continue
    if r["labels"].get("t4_perturbed"): hard_with_t4+=1
print(f"hard-anomaly cases with non-empty t4_perturbed: {hard_with_t4}")
