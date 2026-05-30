# PRD: Maximize the provenance `/verify` score (self_test + held-out generalization)

**Branch:** `ralph/verify-score`
**Owner:** Ralph autoloop (Claude Code)
**Backend under test:** `backend/verify.py` (pure, DB-free `verify_chain()`), served at `POST /verify`.
**Grader:** `self_test.py http://localhost:8000/verify` (mirrors the official held-out harness, same per-case formula).

## Background / current state (measured 2026-05-30)

Baseline self_test = **98.5%** (1000 cases). Every hard-rule category is already at **100%**
(circular, clean, cost_anomaly, dangling_parent, mass_balance, parent_hash_mismatch,
replay_within_chain, signature_corrupt, tamper_no_resign, timestamp_inversion,
transformation_implausible, unit_mismatch, unknown_supplier, t4_timing_outlier).

The **entire remaining gap is the T4 statistical-outlier detectors**:

| category            | self_test avg | n  |
|---------------------|--------------:|---:|
| t4_cost_outlier     | 52.9%         | 17 |
| t4_labour_outlier   | 78.6%         | 28 |
| t4_origin_outlier   | 97.4%         | 38 |

Each T4 case has **exactly one** perturbed attestation; scoring is F1 over the perturbed
`attestation_id`s, so each case is effectively all-or-nothing. The detector currently has
≈0 false positives — every lost point is a **miss**, not an over-flag.

## ⚠️ The overfitting trap (hard guardrail)

`self_test.py` runs against `training_corpus.jsonl`, whose labels we have. It is trivial to
inflate the *local* number by tightening thresholds against this exact corpus — but the
**official scored set is held out** and uses the same logic on different data. Cross-validation
(train on 70%, score on 30%, 5 seeds) was run on candidate rules:

- A per-`(root_product, component, action)` "exceeds clean max" rule scores **99.3% on
  self_test** but false-flags **14–20% of held-out clean chains**. Each clean false-positive
  costs 0.35 of that case's score → on the real held-out set this would **lower** the score by
  an estimated **3–4 points**. The 99.3% is an artifact (the max is computed from the same data
  it is tested on → 0 FP by construction).
- A per-`(name, action)` robust-z rule holds **0% held-out clean FP only at z ≳ 4.0**, where it
  recovers very little extra T4 recall.

**Conclusion: ~98.5% is the honest generalizable ceiling.** Reaching exactly 100% on self_test
requires memorizing the specific perturbed `attestation_id`s (or equivalent fine-key fitting),
which provably *hurts* the real submission. **DO NOT overfit.**

## Definition of "done" (real objective)

A change is acceptable **only if it does not regress held-out generalization**:

1. `self_test.py` overall **≥ 98.5%** (never regress), AND
2. **Clean category stays 100.0%** on self_test (zero clean false positives), AND
3. The 5-seed 70/30 cross-validation (`scripts/ralph/cv_check.py`) reports **held-out clean-FP
   chains < 1%**, AND
4. `python3 -m reference_lib.tests.test_golden` passes (byte-exact core intact).

Ship a story only when ALL four hold. Maximize T4 recall **subject to** these constraints.
If a candidate raises self_test but fails the CV guard (3), it is overfitting — reject it.

## Emit `<promise>COMPLETE</promise>` when

Either: every story below `passes: true`, OR a story is provably blocked because the remaining
perturbed nodes are statistically indistinguishable from clean data (document the evidence in
`progress.txt` and stop — do not overfit to close it).
