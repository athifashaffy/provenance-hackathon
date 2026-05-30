import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # for sibling gen_cases

"""Test the coverage GAPS the 1000-case corpus misses: diamonds, anchor-registry
checks, insufficient_data, designation boundaries, degenerate chains, novel attacks.
Each case has hand-computed ground truth; we assert verify matches."""
import sys, copy, json
import gen_cases as G
import verify
from reference_lib.canonical import content_hash

PASS = []; FAIL = []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if (detail and not cond) else ""))

def ids(resp): return {(a["type"], a["attestation_id"]) for a in resp["anomalies"]}
def flagged_ids(resp): return {a["attestation_id"] for a in resp["anomalies"]}

# helpers to build minimal signed nodes
def _sup_for(country):
    # pick a supplier whose clean origin matches `country`, so the origin-outlier
    # detector (raw claimed CA from a normally-foreign supplier) doesn't false-fire
    for s in G.RAW_SUPPLIERS:
        if G.sup_ctry[s].most_common(1)[0][0] == country:
            return s
    return G.random.choice(G.RAW_SUPPLIERS)

def raw(country, mat, qty=10, unit="kg", sup=None, day=1):
    sup = sup or _sup_for(country)
    n = {"attestation_id": G.rid(), "version": "1.0", "supplier_id": sup,
         "timestamp": f"2026-01-{day:02d}T09:00:00Z", "action_type": "raw_material_supply",
         "performed_in_country": country, "parents": [],
         "output": {"name": "raw", "quantity_produced": qty, "unit": unit},
         "costs": {"material_cad": mat, "labour_hours": 0.0, "labour_cost_cad": 0.0}}
    return G.sign(n)

def xform(action, country, children, hrs, lcost, mat=0.0, qty=1, unit="units", month=2):
    sup = G.random.choice(G.ALL_SUPPLIERS)
    parents = [{"attestation_id": c["attestation_id"], "content_hash": content_hash(c),
                "quantity_consumed": 1, "unit": c["output"]["unit"]} for c in children]
    n = {"attestation_id": G.rid(), "version": "1.0", "supplier_id": sup,
         "timestamp": f"2026-{month:02d}-15T14:30:00Z", "action_type": action,
         "performed_in_country": country, "parents": parents,
         "output": {"name": "asm", "quantity_produced": qty, "unit": unit},
         "costs": {"material_cad": mat, "labour_hours": hrs, "labour_cost_cad": lcost}}
    return G.sign(n)

def chain(atts, leaf): return {"product_attestation_id": leaf["attestation_id"], "attestations": atts}

# ============================================================
print("\n### 1. DIAMOND DAGs (0 in corpus) ###")
# legitimate diamond: component consumed by two subassemblies, within budget
c = raw("CA", 100, qty=10, unit="units")               # shared part, produces 10
s1 = xform("subassembly", "CA", [c], 6, 600, month=2)  # consumes 1
s2 = xform("subassembly", "CA", [c], 6, 600, month=2)  # consumes 1
leaf = xform("final_integration", "CA", [s1, s2], 5, 500, month=3)
ch = chain([c, s1, s2, leaf], leaf)
r = verify.verify_chain(ch)
# pct: total = 100 + 600 + 600 + 500 = 1800, all CA -> 100%. c counted ONCE (diamond)
check("diamond legit: pct counts shared node once (100%)", abs(r["canadian_content_percentage"]-100.0)<0.5, f"got {r['canadian_content_percentage']}")
check("diamond legit: no false anomaly", r["chain_valid"] and not r["anomalies"], str(ids(r)))
check("diamond legit: designation product_of_canada", r["designation"]=="product_of_canada", r["designation"])

# diamond mass-balance: shared node produces 2, two consumers take 2 each (total 4 > 2)
c = raw("CA", 100, qty=2, unit="units")
s1 = xform("subassembly", "CA", [c], 6, 600); s1["parents"][0]["quantity_consumed"]=2; s1=G.sign({k:v for k,v in s1.items() if k!="signature"})
s2 = xform("subassembly", "CA", [c], 6, 600); s2["parents"][0]["quantity_consumed"]=2; s2=G.sign({k:v for k,v in s2.items() if k!="signature"})
# fix child hashes for s1,s2 referencing c (c unchanged) already correct; leaf references s1,s2
leaf = xform("final_integration", "CA", [s1, s2], 5, 500)
ch = chain([c, s1, s2, leaf], leaf)
r = verify.verify_chain(ch)
check("diamond mass-balance: flags shared node (global sum 4>2)",
      ("mass_balance_violation", c["attestation_id"]) in ids(r), str([(t,i[:8]) for t,i in ids(r)]))

# ============================================================
print("\n### 2. ANCHOR REGISTRY (0 anchored in corpus) ###")
saved = verify.ANCHORS
try:
    c = raw("CA", 100, qty=10); leaf = xform("final_integration", "CA", [c], 5, 500)
    ch = chain([c, leaf], leaf); pid = leaf["attestation_id"]
    # 2a clean anchored: correct hash + correct product -> NO anomaly
    verify.ANCHORS = {leaf["attestation_id"]: {"attestation_id": leaf["attestation_id"], "content_hash": content_hash(leaf), "product_id": pid}}
    r = verify.verify_chain(ch)
    check("anchored clean: no false positive", r["chain_valid"] and not r["anomalies"], str(ids(r)))
    # 2b anchor_mismatch: registered hash differs from actual
    verify.ANCHORS = {leaf["attestation_id"]: {"attestation_id": leaf["attestation_id"], "content_hash": "00"*32, "product_id": pid}}
    r = verify.verify_chain(ch)
    check("anchor_mismatch detected", ("anchor_mismatch", leaf["attestation_id"]) in ids(r), str(ids(r)))
    # 2c replay_cross_chain: correct hash but different product_id
    verify.ANCHORS = {c["attestation_id"]: {"attestation_id": c["attestation_id"], "content_hash": content_hash(c), "product_id": "att-some-other-product-00"}}
    r = verify.verify_chain(ch)
    check("replay_cross_chain detected", ("replay_cross_chain", c["attestation_id"]) in ids(r), str(ids(r)))
finally:
    verify.ANCHORS = saved

# ============================================================
print("\n### 3. insufficient_data / total cost 0 ###")
c = raw("CA", 0.0, qty=10); leaf = xform("final_integration", "CA", [c], 5, 0.0)
ch = chain([c, leaf], leaf); r = verify.verify_chain(ch)
check("zero-cost chain: pct 0, designation none", r["canadian_content_percentage"]==0.0 and r["designation"]=="none", f"{r['canadian_content_percentage']}/{r['designation']}")
check("zero-cost chain: no spurious hard anomaly", r["chain_valid"], str(ids(r)))

# ============================================================
print("\n### 4. DESIGNATION BOUNDARIES ###")
def two_node(ca_cost, foreign_cost, last_country="CA", hrs=5):
    fr = raw("US", foreign_cost, qty=10)
    leaf = xform("final_integration", last_country, [fr], hrs, ca_cost)
    return chain([fr, leaf], leaf)
# exactly 98.0 -> product_of_canada (CA labour 98, foreign mat 2)
r = verify.verify_chain(two_node(98.0, 2.0)); check("pct exactly 98.0 -> product_of_canada", r["designation"]=="product_of_canada", f"{r['canadian_content_percentage']}/{r['designation']}")
# 97.9 -> made_in_canada
r = verify.verify_chain(two_node(97.9, 2.1)); check("pct 97.9 -> made_in_canada", r["designation"]=="made_in_canada", f"{r['canadian_content_percentage']}/{r['designation']}")
# exactly 51.0 -> made_in_canada
r = verify.verify_chain(two_node(51.0, 49.0)); check("pct exactly 51.0 -> made_in_canada", r["designation"]=="made_in_canada", f"{r['canadian_content_percentage']}/{r['designation']}")
# 50.9 -> none
r = verify.verify_chain(two_node(50.9, 49.1)); check("pct 50.9 -> none", r["designation"]=="none", f"{r['canadian_content_percentage']}/{r['designation']}")
# high pct but last transform NOT in CA -> none
r = verify.verify_chain(two_node(99.0, 1.0, last_country="US")); check("99% but last transform US -> none", r["designation"]=="none", f"{r['canadian_content_percentage']}/{r['designation']}")
# substantial transformation boundary: labour_hours exactly 4 qualifies; 3.9 does not
r = verify.verify_chain(two_node(99.0, 1.0, hrs=4.0)); check("labour_hours==4 qualifies (product_of_canada)", r["designation"]=="product_of_canada", f"{r['designation']}")
r = verify.verify_chain(two_node(99.0, 1.0, hrs=3.9)); check("labour_hours==3.9 NOT substantial -> none", r["designation"]=="none", f"{r['designation']}")

# ============================================================
print("\n### 5. DEGENERATE / SINGLE-NODE ###")
# single raw only -> no substantial transformation -> none
only_raw = raw("CA", 100, qty=10)
r = verify.verify_chain({"product_attestation_id": only_raw["attestation_id"], "attestations":[only_raw]})
check("single raw: designation none (no transform)", r["designation"]=="none" and r["canadian_content_percentage"]==100.0, f"{r['canadian_content_percentage']}/{r['designation']}")
# single final_integration leaf, CA, labour>=4, 100% CA -> product_of_canada
solo = xform("final_integration", "CA", [], 5, 500); solo["parents"]=[]; solo=G.sign({k:v for k,v in solo.items() if k!="signature"})
r = verify.verify_chain({"product_attestation_id": solo["attestation_id"], "attestations":[solo]})
# note: final_integration with NO parents is also "transformation_implausible" per our rule
check("solo final_integration: 100% CA", abs(r["canadian_content_percentage"]-100.0)<0.5, f"{r['canadian_content_percentage']}")
print("       (solo-leaf anomalies:", [(a['type']) for a in r['anomalies']], ")")
# empty chain
r = verify.verify_chain({"product_attestation_id":"att-x","attestations":[]})
check("empty chain: no crash, none", r["designation"]=="none", str(r))
# product id not in chain
r = verify.verify_chain({"product_attestation_id":"att-missing","attestations":[raw("CA",100)]})
check("product id absent: no crash", isinstance(r.get("anomalies"),list), str(r))

# ============================================================
print("\n### 6. NOVEL ATTACK CLASSES (spec: examples not exhaustive) ###")
# self-parent (node references itself) -> should be caught as cycle
c = raw("CA",100,qty=10); leaf = xform("final_integration","CA",[c],5,500)
leaf["parents"].append({"attestation_id": leaf["attestation_id"], "content_hash": content_hash(leaf), "quantity_consumed":1,"unit":"units"})
leaf = G.sign({k:v for k,v in leaf.items() if k!="signature"})
r = verify.verify_chain(chain([c,leaf],leaf))
check("self-parent -> circular_reference", any(a["type"]=="circular_reference" for a in r["anomalies"]), str([a['type'] for a in r['anomalies']]))
# duplicate parent reference (same parent twice) -> mass balance if over budget
c = raw("CA",100,qty=1,unit="units"); leaf = xform("final_integration","CA",[c],5,500)
leaf["parents"].append(copy.deepcopy(leaf["parents"][0]))  # consume c twice (total 2 > produced 1)
leaf = G.sign({k:v for k,v in leaf.items() if k!="signature"})
r = verify.verify_chain(chain([c,leaf],leaf))
check("duplicate-parent over-consumption -> mass_balance", any(a["type"]=="mass_balance_violation" for a in r["anomalies"]), str([a['type'] for a in r['anomalies']]))
# negative cost
c = raw("CA",-50,qty=10); leaf = xform("final_integration","CA",[c],5,500)
r = verify.verify_chain(chain([c,leaf],leaf))
check("negative cost: no crash", isinstance(r["canadian_content_percentage"],(int,float)), str(r))
print("       (negative-cost handling: pct=%s designation=%s anomalies=%s)"%(r["canadian_content_percentage"],r["designation"],[a['type'] for a in r['anomalies']]))

print(f"\n==== GAP TEST: {len(PASS)} passed, {len(FAIL)} failed ====")
if FAIL: print("FAILURES:", FAIL)
