import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
_sys.path.insert(0, _os.path.join(ROOT, "backend"))

"""Validate reference_lib parity + deep-analyze the training corpus."""
import json, os, sys, statistics
from collections import defaultdict, Counter

from reference_lib.canonical import canonical_serialize, content_hash
from reference_lib.crypto import verify_attestation

keys = json.load(open(f"{ROOT}/registry/supplier_public_keys.json"))["keys"]
anchors_raw = json.load(open(f"{ROOT}/registry/anchor_registry.json"))
anchors = {a["attestation_id"]: a for a in anchors_raw["anchors"]}

print("=" * 70)
print("PART 1: Reference lib parity on worked-example")
print("=" * 70)
we = json.load(open(f"{ROOT}/worked-example/recovery_drone_chain.json"))
atts = {a["attestation_id"]: a for a in we["attestations"]}
sig_ok = 0; hash_ok = 0; hash_tot = 0
for a in we["attestations"]:
    pk = keys.get(a["supplier_id"])
    v = verify_attestation(a, pk) if pk else False
    sig_ok += v
    # check parent content_hash links
    for p in a.get("parents", []):
        hash_tot += 1
        parent = atts.get(p["attestation_id"])
        if parent:
            ch = content_hash(parent)
            if ch == p["content_hash"]:
                hash_ok += 1
            else:
                print(f"  HASH MISMATCH {p['attestation_id']}: computed {ch[:16]} vs link {p['content_hash'][:16]}")
print(f"signatures verified: {sig_ok}/{len(we['attestations'])}")
print(f"parent content_hash links matched: {hash_ok}/{hash_tot}")
# anchor check on worked example
anc_match = 0; anc_tot = 0
for a in we["attestations"]:
    if a["attestation_id"] in anchors:
        anc_tot += 1
        if content_hash(a) == anchors[a["attestation_id"]]["content_hash"]:
            anc_match += 1
print(f"anchored worked-example atts content_hash matched: {anc_match}/{anc_tot}")

print("\n" + "=" * 70)
print("PART 2: Corpus structure + per-family signal analysis")
print("=" * 70)
CORPUS = f"{ROOT}/training_corpus.jsonl"
rows = [json.loads(l) for l in open(CORPUS)]
print(f"total rows: {len(rows)}")

# label field shapes
fam_examples = defaultdict(list)
for r in rows:
    fam = r["labels"].get("attack", "clean")
    fam_examples[fam].append(r)

# Show one example's label + anomaly entries per family
for fam in sorted(fam_examples):
    ex = fam_examples[fam][0]
    lab = ex["labels"]
    print(f"\n--- {fam} (n={len(fam_examples[fam])}) ---")
    print("  label keys:", list(lab.keys()))
    print("  chain_valid:", lab.get("chain_valid"), "| designation:", lab.get("designation"),
          "| pct:", lab.get("canadian_content_percentage"))
    anoms = lab.get("anomalies", [])
    if anoms:
        print("  anomalies:", json.dumps(anoms)[:300])
    t4 = lab.get("t4_perturbed", [])
    if t4:
        print("  t4_perturbed ids:", t4)
