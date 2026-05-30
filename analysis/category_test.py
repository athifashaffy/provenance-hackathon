import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Test the FIVE challenge categories head-on, with emphasis on category 5
(incomplete data / missing fields) which has ZERO coverage in the corpus.
Goal: correct detection AND 'without falling over' (no exceptions/500s)."""
import sys, copy, json, traceback
import gen_cases as G
import verify
from reference_lib.canonical import content_hash

PASS=[]; FAIL=[]
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if (detail and not cond) else ""))

def safe_verify(sub, name):
    """category 5 core: must NOT raise, ever."""
    try:
        r = verify.verify_chain(sub)
        # response shape must be intact
        ok = all(k in r for k in ("product_attestation_id","canadian_content_percentage","designation","chain_valid","anomalies"))
        return r, ok, None
    except Exception as e:
        return None, False, traceback.format_exc()

def ids(r): return {(a["type"], a["attestation_id"]) for a in (r["anomalies"] if r else [])}
def types(r): return {a["type"] for a in (r["anomalies"] if r else [])}

def raw(country, mat, qty=10, unit="kg"):
    for s in G.RAW_SUPPLIERS:
        if G.sup_ctry[s].most_common(1)[0][0]==country: sup=s; break
    else: sup=G.random.choice(G.RAW_SUPPLIERS)
    return G.sign({"attestation_id":G.rid(),"version":"1.0","supplier_id":sup,
        "timestamp":"2026-01-05T09:00:00Z","action_type":"raw_material_supply",
        "performed_in_country":country,"parents":[],
        "output":{"name":"raw","quantity_produced":qty,"unit":unit},
        "costs":{"material_cad":mat,"labour_hours":0.0,"labour_cost_cad":0.0}})

def leaf_over(children, country="CA", hrs=5, lc=500):
    n=G.make_transform("final_integration",country=="CA" and True or False,children,hrs) if False else None
    sup=G.random.choice(G.ALL_SUPPLIERS)
    parents=[{"attestation_id":c["attestation_id"],"content_hash":content_hash(c),"quantity_consumed":1,"unit":c["output"]["unit"]} for c in children]
    return G.sign({"attestation_id":G.rid(),"version":"1.0","supplier_id":sup,
        "timestamp":"2026-03-15T14:30:00Z","action_type":"final_integration",
        "performed_in_country":country,"parents":parents,
        "output":{"name":"asm","quantity_produced":1,"unit":"units"},
        "costs":{"material_cad":0.0,"labour_hours":hrs,"labour_cost_cad":lc}})

def simple_chain(country="CA"):
    c=raw(country,100); l=leaf_over([c],country);
    return {"product_attestation_id":l["attestation_id"],"attestations":[c,l]}, c, l

print("\n### CATEGORY 1: Integrity violations (modified-after-signing, unregistered signer) ###")
# 1a modified after signing
sub,c,l=simple_chain(); l["costs"]["labour_cost_cad"]=99999  # tamper post-sign
r,ok,err=safe_verify(sub,"tamper"); check("modified-after-signing -> signature_invalid", "signature_invalid" in types(r), str(types(r)))
# 1b unregistered signer
sub,c,l=simple_chain(); l["supplier_id"]="sup-not-real-123"
r,ok,err=safe_verify(sub,"unregistered"); check("unregistered signer -> signature_unknown_supplier", "signature_unknown_supplier" in types(r), str(types(r)))

print("\n### CATEGORY 2: Replay and reuse ###")
# 2a replay within chain (dup id)
sub,c,l=simple_chain(); sub["attestations"].append(copy.deepcopy(c))
r,ok,err=safe_verify(sub,"dup"); check("duplicate attestation in submission -> replay_within_chain", "replay_within_chain" in types(r), str(types(r)))
# 2b cross-chain reuse via anchor (attestation anchored to a DIFFERENT product)
saved=verify.ANCHORS
sub,c,l=simple_chain()
verify.ANCHORS={c["attestation_id"]:{"attestation_id":c["attestation_id"],"content_hash":content_hash(c),"product_id":"att-different-product-xyz"}}
r,ok,err=safe_verify(sub,"xchain"); check("attestation reused across products -> replay_cross_chain", "replay_cross_chain" in types(r), str(types(r)))
verify.ANCHORS=saved

print("\n### CATEGORY 3: Quantity inconsistencies (consumed > produced) ###")
c=raw("CA",100,qty=1,unit="units"); l=leaf_over([c]); l["parents"][0]["quantity_consumed"]=5; l=G.sign({k:v for k,v in l.items() if k!="signature"})
sub={"product_attestation_id":l["attestation_id"],"attestations":[c,l]}
r,ok,err=safe_verify(sub,"qty"); check("consumed > produced -> mass_balance_violation on parent", ("mass_balance_violation",c["attestation_id"]) in ids(r), str(ids(r)))

print("\n### CATEGORY 4: Structural (missing ref, broken link, impossible ordering) ###")
# 4a dangling/missing reference
sub,c,l=simple_chain(); l["parents"].append({"attestation_id":"att-ghost-000","content_hash":"00"*32,"quantity_consumed":1,"unit":"units"}); l=G.sign({k:v for k,v in l.items() if k!="signature"})
r,ok,err=safe_verify(sub,"dangling"); check("missing reference -> dangling_parent", "dangling_parent" in types(r), str(types(r)))
# 4b broken hash link
sub,c,l=simple_chain(); l["parents"][0]["content_hash"]="ff"*32; l=G.sign({k:v for k,v in l.items() if k!="signature"})
r,ok,err=safe_verify(sub,"hash"); check("broken hash link -> parent_hash_mismatch", "parent_hash_mismatch" in types(r), str(types(r)))
# 4c impossible ordering (child before parent)
sub,c,l=simple_chain(); l["timestamp"]="2020-01-01T14:30:00Z"; l=G.sign({k:v for k,v in l.items() if k!="signature"})
r,ok,err=safe_verify(sub,"order"); check("impossible ordering -> timestamp_inversion", "timestamp_inversion" in types(r), str(types(r)))
# 4d cycle
sub,c,l=simple_chain(); c["parents"]=[{"attestation_id":l["attestation_id"],"content_hash":content_hash(l),"quantity_consumed":1,"unit":"units"}]; c=G.sign({k:v for k,v in c.items() if k!="signature"})
sub["attestations"]=[c,l]
r,ok,err=safe_verify(sub,"cycle"); check("cycle -> circular_reference", "circular_reference" in types(r), str(types(r)))

print("\n### CATEGORY 5: INCOMPLETE DATA — must not fall over (0 corpus coverage) ###")
# helper: take a clean chain and DELETE a field from one node, must not crash
FIELDS = ["supplier_id","timestamp","action_type","performed_in_country","parents","output","costs","version","attestation_id"]
NESTED = [("output","quantity_produced"),("output","unit"),("output",None),
          ("costs","material_cad"),("costs","labour_cost_cad"),("costs","labour_hours"),("costs",None)]
crashes=0
for fld in FIELDS:
    sub,c,l=simple_chain()
    victim = l if fld!="attestation_id" else c  # don't break leaf id (product ref)
    victim.pop(fld, None)
    r,ok,err=safe_verify(sub, f"drop {fld}")
    if err: crashes+=1; print(f"     CRASH on missing '{fld}':\n{err}")
    check(f"missing top-level '{fld}': no crash, valid response", ok and err is None, "crashed" if err else "bad shape")
for parent,child in NESTED:
    sub,c,l=simple_chain()
    if child is None: l[parent]=None
    else:
        if isinstance(l.get(parent),dict): l[parent].pop(child,None)
    r,ok,err=safe_verify(sub, f"drop {parent}.{child}")
    if err: crashes+=1; print(f"     CRASH on missing '{parent}.{child}':\n{err}")
    check(f"missing nested '{parent}.{child}': no crash", ok and err is None, "crashed" if err else "bad shape")

# wholly malformed inputs
for label, sub in [
    ("attestations not a list", {"product_attestation_id":"x","attestations":"nope"}),
    ("attestation is null", {"product_attestation_id":"x","attestations":[None]}),
    ("attestation is a string", {"product_attestation_id":"x","attestations":["just a string"]}),
    ("no product_attestation_id", {"attestations":[]}),
    ("totally empty object", {}),
    ("costs is null", {"product_attestation_id":"x","attestations":[{"attestation_id":"x","supplier_id":"sup-0001","action_type":"raw_material_supply","performed_in_country":"CA","parents":[],"output":None,"costs":None,"timestamp":"2026-01-01T09:00:00Z","version":"1.0"}]}),
]:
    r,ok,err=safe_verify(sub,label)
    if err: crashes+=1; print(f"     CRASH on '{label}':\n{err}")
    check(f"malformed input '{label}': no crash", ok and err is None, "crashed" if err else "bad shape")

print(f"\n==== CATEGORY TEST: {len(PASS)} passed, {len(FAIL)} failed | crashes={crashes} ====")
if FAIL: print("FAILURES:", FAIL)
