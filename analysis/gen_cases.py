import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Synthesize fresh, properly-signed test cases with INDEPENDENT ground-truth
labels, then score verify_chain against them. Tests generalization + FP safety."""
import json, sys, os, random, hashlib
random.seed(1234)

from reference_lib.canonical import content_hash
from reference_lib.crypto import sign_attestation, verify_attestation
from verify import verify_chain

PRIV = json.load(open(f"{ROOT}/private_keys/supplier_private_keys.json"))["keys"]
PUB = json.load(open(f"{ROOT}/registry/supplier_public_keys.json"))["keys"]

# learn clean per-supplier country + cost/labour distributions from the corpus
from collections import defaultdict, Counter
import statistics
rows = [json.loads(l) for l in open(f"{ROOT}/training_corpus.jsonl")]
clean = [r for r in rows if r["labels"].get("attack", "clean") == "clean"]
sup_ctry = defaultdict(Counter)
raw_costs = []
lab_hours = defaultdict(list)
lab_rate = []
units_pool = Counter()
for r in clean:
    for a in r["chain"]["attestations"]:
        c = a["costs"]
        if a["action_type"] == "raw_material_supply":
            sup_ctry[a["supplier_id"]][a["performed_in_country"]] += 1
            if c["material_cad"] > 0:
                raw_costs.append(c["material_cad"])
            units_pool[a["output"]["unit"]] += 1
        elif c.get("labour_hours", 0) > 0:
            lab_hours[a["action_type"]].append(c["labour_hours"])
            lab_rate.append(c["labour_cost_cad"] / c["labour_hours"])

RAW_SUPPLIERS = [s for s in sup_ctry if s in PRIV]
ALL_SUPPLIERS = [s for s in PUB if s in PRIV]
UNITS = list(units_pool)
hours_p = lambda act, q: sorted(lab_hours[act])[min(len(lab_hours[act]) - 1, int(q * len(lab_hours[act])))]


def rid():
    return "att-" + "".join(random.choice("0123456789abcdef") for _ in range(24))


def sign(node):
    sk = PRIV[node["supplier_id"]]
    return sign_attestation(node, sk)


def _date(tier):
    # strictly increasing date by tier so parents always pre-date children
    # raw=Jan, component=early Feb, subassembly=late Feb, final=March
    base = {0: (1, 1, 25), 1: (2, 1, 10), 2: (2, 15, 25), 3: (3, 1, 15)}[tier]
    m, lo, hi = base
    return f"2026-{m:02d}-{random.randint(lo, hi):02d}"


def make_raw():
    # pick a supplier and use one of ITS clean countries (keeps origin consistent)
    sup = random.choice(RAW_SUPPLIERS)
    country = random.choice(list(sup_ctry[sup].elements()))
    qty = random.choice([4, 8, 10, 12, 20, 50, 100])  # ample, so single consumer never over-draws
    node = {
        "attestation_id": rid(), "version": "1.0", "supplier_id": sup,
        "timestamp": f"{_date(0)}T09:00:00Z", "action_type": "raw_material_supply",
        "performed_in_country": country, "parents": [],
        "output": {"name": "Raw Part", "quantity_produced": qty, "unit": random.choice(UNITS)},
        "costs": {"material_cad": round(random.choice(raw_costs), 2), "labour_hours": 0.0, "labour_cost_cad": 0.0},
    }
    return sign(node)


def make_transform(action, children, ca, tier):
    sup = random.choice(ALL_SUPPLIERS)
    country = "CA" if ca else random.choice(["US", "CN", "JP", "TW", "DE", "GB", "KR", "FR"])
    hrs = round(random.uniform(hours_p(action, .1), hours_p(action, .9)), 1)
    rate = round(random.uniform(60, 110), 2)
    parents = []
    for ch in children:
        parents.append({
            "attestation_id": ch["attestation_id"],
            "content_hash": content_hash(ch),
            # consume at most what the child produced (single consumer => mass-balanced)
            "quantity_consumed": random.choice([1, min(2, ch["output"]["quantity_produced"])]),
            "unit": ch["output"]["unit"],
        })
    node = {
        "attestation_id": rid(), "version": "1.0", "supplier_id": sup,
        "timestamp": f"{_date(tier)}T14:30:00Z", "action_type": action,
        "performed_in_country": country, "parents": parents,
        "output": {"name": "Assembly", "quantity_produced": 1, "unit": "units"},
        "costs": {"material_cad": 0.0, "labour_hours": hrs, "labour_cost_cad": round(hrs * rate, 1)},
    }
    return sign(node)


def gen_clean_chain():
    """Build a TREE (each node consumed by exactly one parent => mass-balanced)
    with strictly increasing timestamps by tier."""
    ca = random.random() < 0.55
    n_raw = random.randint(4, 10)
    raws = [make_raw() for _ in range(n_raw)]
    random.shuffle(raws)
    # partition raws into disjoint groups, each feeding one component
    mids = []
    i = 0
    comp_group = raws[: max(2, n_raw // 2)]
    rest = raws[len(comp_group):]
    comp = make_transform("component_manufacture", comp_group, ca, 1)
    mids.append(comp)
    leaf_children = [comp] + rest
    if random.random() < 0.4 and len(rest) >= 2:
        sub_group = rest[:2]
        sub = make_transform("subassembly", [comp] + sub_group, ca, 2)
        mids.append(sub)
        leaf_children = [sub] + rest[2:]
    leaf = make_transform("final_integration", leaf_children, ca, 3)
    atts = raws + mids + [leaf]
    random.shuffle(atts)
    return {"product_attestation_id": leaf["attestation_id"], "attestations": atts}, leaf["attestation_id"]


# ---- independent ground-truth labeler (mirrors spec, NOT verify.py) ----
TRANSFORM = {"component_manufacture", "subassembly", "final_integration"}
def label_pct_desig(atts, pid):
    total = can = 0.0
    for a in atts:
        c = a["costs"]; nc = c["material_cad"] + c["labour_cost_cad"]
        total += nc
        if a["performed_in_country"] == "CA": can += nc
    if total <= 0: return 0.0, "none"
    pct = can / total * 100
    byid = {a["attestation_id"]: a for a in atts}
    # BFS from leaf for last substantial transformation
    from collections import deque
    last = None; seen = {pid}; q = deque([pid])
    while q:
        cur = q.popleft(); nd = byid.get(cur)
        if not nd: continue
        if nd["action_type"] in TRANSFORM and nd["costs"]["labour_hours"] >= 4:
            last = nd; break
        for p in nd.get("parents", []):
            if p["attestation_id"] not in seen:
                seen.add(p["attestation_id"]); q.append(p["attestation_id"])
    if last is None or last["performed_in_country"] != "CA": d = "none"
    elif pct >= 98: d = "product_of_canada"
    elif pct >= 51: d = "made_in_canada"
    else: d = "none"
    return round(pct, 2), d


def base_label(chain, pid, attack=None, anomalies=None, t4=None):
    pct, desig = label_pct_desig(chain["attestations"], pid)
    lab = {"product_attestation_id": pid, "canadian_content_percentage": pct,
           "designation": desig, "chain_valid": not anomalies, "anomalies": anomalies or [],
           "t4_perturbed": t4 or []}
    if attack: lab["attack"] = attack
    return lab


# ---- attack injectors (mutate a clean chain; re-sign unless noted) ----
def pick_transform(chain, actions=TRANSFORM, with_parents=True):
    cands = [a for a in chain["attestations"] if a["action_type"] in actions and (not with_parents or a["parents"])]
    return random.choice(cands) if cands else None

def resign(node):
    node.pop("signature", None)
    s = sign(node)
    node.clear(); node.update(s)

def rebuild(chain):
    """Recompute every parents[].content_hash from current parent content and
    re-sign bottom-up, so the ONLY anomaly left is the one we intentionally
    injected (mirrors how the real generator emits a self-consistent chain)."""
    byid = {a["attestation_id"]: a for a in chain["attestations"]}
    order, seen = [], set()
    def visit(nid):
        if nid in seen or nid not in byid: return
        seen.add(nid)
        for p in byid[nid].get("parents", []):
            visit(p["attestation_id"])
        order.append(nid)
    for a in chain["attestations"]:
        visit(a["attestation_id"])
    for nid in order:  # parents before children
        n = byid[nid]
        for p in n.get("parents", []):
            par = byid.get(p["attestation_id"])
            if par is not None:
                p["content_hash"] = content_hash(par)
        if n["supplier_id"] in PRIV:
            resign(n)

def inject(kind, chain, pid):
    byid = {a["attestation_id"]: a for a in chain["attestations"]}
    # ---- semantic/statistical attacks: mutate then rebuild for a consistent chain ----
    if kind == "mass_balance":
        n = pick_transform(chain)
        if not n: return None
        p = n["parents"][0]; parent = byid[p["attestation_id"]]
        p["quantity_consumed"] = parent["output"]["quantity_produced"] + random.choice([1, 2, 5])
        rebuild(chain)
        return base_label(chain, pid, kind, [{"type": "mass_balance_violation", "attestation_id": parent["attestation_id"]}])
    if kind == "unit_mismatch":
        n = pick_transform(chain)
        if not n: return None
        n["parents"][0]["unit"] = "zz"
        rebuild(chain)
        return base_label(chain, pid, kind, [{"type": "unit_mismatch", "attestation_id": n["attestation_id"]}])
    if kind == "timestamp_inversion":
        n = pick_transform(chain)
        if not n: return None
        n["timestamp"] = "2020-01-01T14:30:00Z"
        rebuild(chain)
        return base_label(chain, pid, kind, [{"type": "timestamp_inversion", "attestation_id": n["attestation_id"]}])
    if kind == "cost_anomaly":
        n = pick_transform(chain, with_parents=False)
        if not n: return None
        n["costs"]["labour_cost_cad"] = round(n["costs"]["labour_hours"] * 1000, 1)
        rebuild(chain)
        return base_label(chain, pid, kind, [{"type": "cost_anomaly", "attestation_id": n["attestation_id"]}])
    if kind == "transformation_implausible":
        n = pick_transform(chain)
        if not n: return None
        n["parents"] = []
        rebuild(chain)
        return base_label(chain, pid, kind, [{"type": "transformation_implausible", "attestation_id": n["attestation_id"]}])
    if kind == "unknown_supplier":
        n = random.choice(chain["attestations"])
        n["supplier_id"] = "sup-ghost-" + str(random.randint(1000, 9999))
        rebuild(chain)  # fixes consumers' hashes; ghost node simply isn't re-signed
        return base_label(chain, pid, kind, [{"type": "signature_unknown_supplier", "attestation_id": n["attestation_id"]}])
    # ---- hash/signature attacks: rebuild a clean chain first, then break one thing ----
    if kind == "signature_corrupt":
        rebuild(chain)
        n = random.choice(chain["attestations"])
        v = list(n["signature"]["value"]); v[5] = "A" if v[5] != "A" else "B"
        n["signature"]["value"] = "".join(v)
        return base_label(chain, pid, kind, [{"type": "signature_invalid", "attestation_id": n["attestation_id"]}])
    if kind == "parent_hash_mismatch":
        rebuild(chain)
        n = pick_transform(chain)
        if not n: return None
        n["parents"][0]["content_hash"] = "deadbeef" * 8
        resign(n)  # valid signature over the (now-wrong) reference
        return base_label(chain, pid, kind, [{"type": "parent_hash_mismatch", "attestation_id": n["attestation_id"]}])
    if kind == "dangling_parent":
        rebuild(chain)
        n = pick_transform(chain)
        if not n: return None
        n["parents"].append({"attestation_id": "att-doesnotexist000000000000", "content_hash": "00"*32, "quantity_consumed": 1, "unit": "units"})
        resign(n)
        return base_label(chain, pid, kind, [{"type": "dangling_parent", "attestation_id": n["attestation_id"]}])
    if kind == "circular":
        rebuild(chain)
        # add the leaf as a parent of one of the leaf's OWN direct children, so the
        # only downstream-hash break lands on the leaf == the circular_reference id
        leaf = byid[pid]
        child_ids = [p["attestation_id"] for p in leaf["parents"]]
        if not child_ids: return None
        c = byid[random.choice(child_ids)]
        c["parents"].append({"attestation_id": pid, "content_hash": content_hash(leaf), "quantity_consumed": 1, "unit": "units"})
        resign(c)
        return base_label(chain, pid, kind, [{"type": "circular_reference", "attestation_id": pid}])
    if kind == "tamper_no_resign":
        rebuild(chain)
        n = pick_transform(chain)
        if not n: return None
        parent = byid[n["parents"][0]["attestation_id"]]
        parent["costs"]["material_cad"] += 999  # tamper content, do NOT resign
        return base_label(chain, pid, kind, [
            {"type": "signature_invalid", "attestation_id": parent["attestation_id"]},
            {"type": "parent_hash_mismatch", "attestation_id": n["attestation_id"]}])
    # ---- t4 statistical: perturb one field, rebuild so nothing else changes ----
    if kind == "t4_timing":
        n = random.choice(chain["attestations"])
        hh = random.randint(0, 23); mm = random.randint(0, 59); ss = random.randint(0, 59)
        n["timestamp"] = n["timestamp"].split("T")[0] + f"T{hh:02d}:{mm:02d}:{ss:02d}Z"
        rebuild(chain)
        return base_label(chain, pid, kind, [], [n["attestation_id"]])
    if kind == "t4_labour":
        n = pick_transform(chain, {"component_manufacture", "subassembly"}, with_parents=False)
        if not n: return None
        act = n["action_type"]; n["costs"]["labour_hours"] = round(hours_p(act, .99) * random.uniform(1.5, 2.5), 1)
        n["costs"]["labour_cost_cad"] = round(n["costs"]["labour_hours"] * random.uniform(70, 100), 1)
        rebuild(chain)
        return base_label(chain, pid, kind, [], [n["attestation_id"]])
    if kind == "t4_cost":
        n = pick_transform(chain, {"component_manufacture"}, with_parents=False)
        if not n: return None
        n["costs"]["labour_cost_cad"] = round(n["costs"]["labour_hours"] * random.uniform(112, 122), 1)
        rebuild(chain)
        return base_label(chain, pid, kind, [], [n["attestation_id"]])
    if kind == "t4_origin":
        raws = [a for a in chain["attestations"] if a["action_type"] == "raw_material_supply"]
        foreign_sups = [s for s in RAW_SUPPLIERS if sup_ctry[s].get("CA", 0) / sum(sup_ctry[s].values()) < 0.05 and sum(sup_ctry[s].values()) >= 5]
        if not raws or not foreign_sups: return None
        n = random.choice(raws); n["supplier_id"] = random.choice(foreign_sups); n["performed_in_country"] = "CA"
        rebuild(chain)
        return base_label(chain, pid, kind, [], [n["attestation_id"]])
    return None


# ---- scoring (harness formula) ----
PCT_TOL, PCT_ZERO = 0.5, 5.0
def _ids_by(anoms):
    d = {}
    for a in anoms or []:
        d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
    return d
def score_case(kind, lab, resp):
    if kind and kind.startswith("t4_"):
        truth = set(lab["t4_perturbed"]); flagged = {a["attestation_id"] for a in resp.get("anomalies", [])}
        tp = len(truth & flagged); prec = tp/len(flagged) if flagged else 0; rec = tp/len(truth) if truth else 1
        return 2*prec*rec/(prec+rec) if (prec+rec) else 0
    diff = abs(float(resp.get("canadian_content_percentage", -999)) - lab["canadian_content_percentage"])
    pct = 1.0 if diff <= PCT_TOL else max(0.0, 1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
    desig = 1.0 if resp.get("designation") == lab["designation"] else 0.0
    em, rm = _ids_by(lab["anomalies"]), _ids_by(resp.get("anomalies")); ei, ri = set(em), set(rm); tp = ei & ri
    if not ei and not ri: f1 = 1.0
    elif not ei or not ri: f1 = 0.0
    else:
        pr, rc = len(tp)/len(ri), len(tp)/len(ei); f1 = 2*pr*rc/(pr+rc) if (pr+rc) else 0.0
    classif = (sum(1 for i in tp if em[i] & rm[i])/len(tp)) if tp else (1.0 if not ei else 0.0)
    return 0.30*pct + 0.35*f1 + 0.20*desig + 0.15*classif


N_CLEAN = int(sys.argv[1]) if len(sys.argv) > 1 else 600
PER_ATTACK = int(sys.argv[2]) if len(sys.argv) > 2 else 40
HARD = ["signature_corrupt", "unknown_supplier", "mass_balance", "unit_mismatch", "parent_hash_mismatch",
        "dangling_parent", "circular", "timestamp_inversion", "cost_anomaly", "transformation_implausible", "tamper_no_resign"]
T4 = ["t4_timing", "t4_labour", "t4_cost", "t4_origin"]

agg = defaultdict(lambda: [0.0, 0])
fp_clean = []
misses = defaultdict(list)
total = 0.0; ncases = 0

for _ in range(N_CLEAN):
    chain, pid = gen_clean_chain()
    lab = base_label(chain, pid)
    resp = verify_chain(chain)
    s = score_case(None, lab, resp); total += s; ncases += 1; agg["clean"][0] += s; agg["clean"][1] += 1
    if resp["anomalies"]:
        fp_clean.append((pid, [(a["type"], a["details"]) for a in resp["anomalies"]]))

for kind in HARD + T4:
    made = 0; tries = 0
    while made < PER_ATTACK and tries < PER_ATTACK * 4:
        tries += 1
        chain, pid = gen_clean_chain()
        lab = inject(kind, chain, pid)
        if lab is None: continue
        made += 1
        resp = verify_chain(chain)
        s = score_case(kind if kind.startswith("t4_") else None, lab, resp)
        total += s; ncases += 1; agg[kind][0] += s; agg[kind][1] += 1
        if s < 0.8 and len(misses[kind]) < 2:
            misses[kind].append((round(s,2), lab, [(a["type"], a["attestation_id"][:10]) for a in resp.get("anomalies", [])]))

print(f"\nSYNTHETIC overall: {total/ncases*100:.1f}%  ({ncases} fresh cases)\n")
print(f"{'category':28s}  avg     n")
for k in sorted(agg):
    v = agg[k]; print(f"{k:28s}  {v[0]/v[1]*100:5.1f}  {v[1]:4d}")
print(f"\nCLEAN false positives: {len(fp_clean)}/{agg['clean'][1]}")
for pid, an in fp_clean[:8]:
    print("  FP", pid[:12], an)
if "-v" in sys.argv:
    print("\n=== hard/t4 misses ===")
    for k, lst in misses.items():
        for s, lab, got in lst:
            print(f"[{k}] score={s} exp={[(a['type'],a['attestation_id'][:10]) for a in lab['anomalies']]} t4={[t[:10] for t in lab['t4_perturbed']]} got={got}")
