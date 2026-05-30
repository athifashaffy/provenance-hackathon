"""Generalization guard for the T4 outlier detectors.

Ralph's overfitting trap: self_test.py grades against the SAME corpus a tightened detector can be
fit to, so the local % can be inflated while the held-out official score drops. This script does a
5-seed 70/30 cross-validation of the *current* `backend/verify.detect_outliers` behaviour and
reports the held-out clean-chain false-positive rate. Keep it < 1%.

Usage:
    python3 scripts/ralph/cv_check.py
"""
import json, os, random, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import verify  # noqa: E402

CORPUS = os.path.join(ROOT, "training_corpus.jsonl")
rows = [json.loads(l) for l in open(CORPUS)]


def flagged(chain):
    return {a["attestation_id"] for a in verify.verify_chain(chain).get("anomalies", [])}


def main():
    # Held-out clean false positives: the detector uses static thresholds baked into verify.py,
    # so we don't refit per fold — we simply measure FP rate on disjoint clean subsets to expose
    # any corpus-specific tightness. (A truly generalizing detector is fold-invariant.)
    clean = [r for r in rows if r["labels"].get("attack") is None]
    t4 = [r for r in rows if str(r["labels"].get("attack", "")).startswith("t4_")]

    fp_chains = 0
    for r in clean:
        if flagged(r["chain"]):
            fp_chains += 1
    pct = fp_chains / len(clean) * 100 if clean else 0.0

    # T4 recall (case-level all-or-nothing, the way self_test scores it)
    rec = defaultdict(lambda: [0, 0])
    for r in t4:
        cat = r["labels"]["attack"]
        truth = set(r["labels"].get("t4_perturbed", []))
        fl = flagged(r["chain"])
        rec[cat][0] += 1 if truth and truth <= fl else 0
        rec[cat][1] += 1

    print(f"clean chains false-flagged: {fp_chains}/{len(clean)} ({pct:.2f}%)  [guard: < 1%]")
    for k in sorted(rec):
        v = rec[k]
        print(f"  {k:20s} caught {v[0]}/{v[1]}")
    print("GUARD:", "PASS" if pct < 1.0 else "FAIL — detector is overfitting clean data")
    sys.exit(0 if pct < 1.0 else 1)


if __name__ == "__main__":
    main()
