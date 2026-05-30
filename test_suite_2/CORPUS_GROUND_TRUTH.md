# Training Corpus — Ground Truth (1,000 cases)

Everything below is measured directly from `training_corpus.jsonl`, not inferred.
This is the authoritative answer to "what does the harness test." The held-out
set is described by the docs as the same logic, a bit harder.

## Headline distributions

- **1,000 cases**: 705 clean, 295 attacks.
- **designation**: none 514, made_in_canada 344, product_of_canada 142.
- **chain_valid**: True 829, False 171.
- A spec-correct percentage + designation implementation reproduces **705/705
  clean cases exactly** (verified), so the deterministic core is fully specified
  by the rules in TECHNICAL_GUIDE §6.

## The 17 `attack` family labels (labels.attack)

| family                       |  n  | chain_valid | carries anomalies[] | carries t4_perturbed |
| ---------------------------- | --: | ----------- | ------------------- | -------------------- |
| clean                        | 705 | True        | no                  | no                   |
| t4_timing_outlier            |  41 | **True**    | **no**              | **yes**              |
| t4_origin_outlier            |  38 | **True**    | **no**              | **yes**              |
| t4_labour_outlier            |  28 | **True**    | **no**              | **yes**              |
| t4_cost_outlier              |  17 | **True**    | **no**              | **yes**              |
| timestamp_inversion          |  20 | False       | yes                 | no                   |
| circular                     |  19 | False       | yes                 | no                   |
| signature_corrupt            |  17 | False       | yes                 | no                   |
| transformation_implausible   |  17 | False       | yes                 | no                   |
| unknown_supplier             |  15 | False       | yes                 | no                   |
| cost_anomaly                 |  15 | False       | yes                 | no                   |
| mass_balance                 |  13 | False       | yes                 | no                   |
| dangling_parent              |  13 | False       | yes                 | no                   |
| parent_hash_mismatch         |  12 | False       | yes                 | no                   |
| unit_mismatch                |  12 | False       | yes                 | no                   |
| replay_within_chain          |  11 | False       | yes                 | no                   |
| tamper_no_resign             |   7 | False       | yes                 | no                   |

Two critical facts this settles:

1. **All four T4 families have `chain_valid: True` and carry NO `anomalies[]`** —
   only a `t4_perturbed` id list. They are scored on a *different path* (F1 over
   ids). My earlier guess that `cost_anomaly`/cost outliers might be T4 was
   **wrong**: `cost_anomaly` is a hard-rule family (chain_valid False, real
   anomaly entry), while `t4_cost_outlier` is the separate statistical one.

2. **Every non-T4 attack family has `chain_valid: False`.** So for hard-rule
   families you SHOULD assert `chain_valid == false`. (This vindicates the
   earlier packed feature on the hard-rule families — but NOT on zero-cost,
   which never appears as its own family here; see below.)

## The exact `anomaly.type` vocabulary (only 11 strings exist)

These are the *only* type strings that appear anywhere in the labels:

```
parent_hash_mismatch        44   timestamp_inversion         39
signature_invalid           24   circular_reference          19
cost_anomaly                19   transformation_implausible  17
signature_unknown_supplier  15   mass_balance_violation      13
dangling_parent             13   unit_mismatch               12
replay_within_chain         11
```

So the canonical type label per family (use these exact strings to win the 0.15
classification bonus):

| family                     | anomaly.type(s) it emits                                        |
| -------------------------- | --------------------------------------------------------------- |
| signature_corrupt          | `signature_invalid`                                             |
| unknown_supplier           | `signature_unknown_supplier` **and** `parent_hash_mismatch`*    |
| parent_hash_mismatch       | `parent_hash_mismatch`                                          |
| tamper_no_resign           | `signature_invalid` + `parent_hash_mismatch` + `cost_anomaly`*  |
| timestamp_inversion        | `timestamp_inversion`                                           |
| circular                   | `circular_reference` + `parent_hash_mismatch` + `timestamp_inversion`* |
| dangling_parent            | `dangling_parent`                                               |
| unit_mismatch              | `unit_mismatch`                                                 |
| mass_balance               | `mass_balance_violation`                                        |
| replay_within_chain        | `replay_within_chain`                                           |
| transformation_implausible | `transformation_implausible`                                    |
| cost_anomaly               | `cost_anomaly`                                                  |

\* **Multi-anomaly families** flag several *distinct attestations*, each with its
own type. Examples measured:
- `circular` (19 cases): each flags 3 attestations → `circular_reference`,
  `parent_hash_mismatch`, `timestamp_inversion` (the cycle also breaks hash
  links and time ordering). To get full F1 you must flag **all three** ids.
- `unknown_supplier` (15): flags the unsigned-by-registry node
  (`signature_unknown_supplier`) **and** typically a downstream
  `parent_hash_mismatch` (10 of 15) because re-signing changed content.
- `tamper_no_resign` (7): the tampered node is flagged `signature_invalid`
  (content changed, signature not refreshed) plus `parent_hash_mismatch` and/or
  `cost_anomaly` on related nodes.

This means F1 is **per-attestation across the whole cluster**, not one flag per
chain — under-flagging a multi-node attack costs recall.

## The four T4 statistical signals (the leaderboard)

T4 cases break no hard rule; `chain_valid` stays True; designation is computed
normally (T4 designations: none 71, made_in_canada 46, product_of_canada 7). You
score purely on flagging the right `t4_perturbed` attestation id(s) by F1. Each
needs a **conditional** model (per `action_type`, per `supplier_id`), not a
global threshold:

- **t4_labour_outlier** (clearest): perturbed `labour_hours` sits far from the
  genuine mean *for that action_type* — measured z median ≈ 4.4, max ≈ 10.6.
  A per-action_type z-score on labour_hours catches most.
- **t4_origin_outlier**: `performed_in_country` is changed (almost always to
  `CA`) for a supplier that, in genuine data, *never operates in that country*.
  Signal = the (supplier_id → performed_in_country) pair is unseen/rare. A
  global country-rarity check misses it (CA is common overall); you must model
  it **conditional on supplier_id**.
- **t4_timing_outlier**: genuine timestamps cluster tightly at hours 9 and 14
  UTC (range 9–14). Perturbed ones scatter across 0–23 (off-hours). Signal =
  hour-of-day outside the genuine working window.
- **t4_cost_outlier** (subtlest): perturbed cost is only mildly off globally
  (z median ≈ 1.0), so a flat z-score is weak. Model cost **conditional on
  action_type** (and ideally the labour_cost/labour_hours ratio), where the
  deviation is sharper.

Genuine per-action distributions (from the 705 clean cases), for calibration:

| action_type           | cost median | cost max | hours median | hours max | top countries           |
| --------------------- | ----------: | -------: | -----------: | --------: | ----------------------- |
| raw_material_supply   |       102.6 |  24075.5 |          0.0 |       0.0 | CN, CA, US, JP, TW      |
| component_manufacture |       451.0 |   1110.8 |          7.0 |      13.7 | CA, TW, DE, GB, JP      |
| subassembly           |      1024.2 |   2629.7 |         12.1 |      23.7 | CA, TW, DE, GB, KR      |
| final_integration     |      2301.9 |   5703.2 |         21.9 |      47.6 | CA, TW, FR, KR, JP      |

(raw_material_supply always has 0 labour hours — a labour_hours > 0 on a raw
node is itself a `transformation_implausible` signal.)

## Corrections this forces to the earlier feature files

1. **Zero-cost / insufficient_data is NOT a corpus attack family.** It never
   appears as its own labelled case. Keep it as a designation rule
   (total cost 0 → none) but do **not** assert `chain_valid: false` for it.
2. **`cost_anomaly` IS a hard-rule family** (chain_valid False), distinct from
   `t4_cost_outlier`. The earlier note's hedge ("likely T4") was wrong.
3. **The accepted-label synonym map should collapse to the 11 real strings.**
   Aliases are fine for robustness, but the bonus only lands on exact matches to
   these 11, so emit these exact strings.
4. **Multi-node families need every offending id flagged** (circular → 3,
   unknown_supplier → up to 2, tamper_no_resign → 2).
5. **There is no `negative_*` numeric family and no explicit
   `invalid_numeric_value` type in the data** — those were inferred. Schema/shape
   violations surface as `transformation_implausible`. Drop the invented numeric
   families from hard-rule assertions (keep them only as defensive input
   validation, not as scored expectations).

## File: how the corpus maps to scoring (recap of self_test.py)

- T4 case (`attack` starts `t4_`): score = F1 over `t4_perturbed` ids.
- Everything else: `0.30*pct + 0.35*anomalyF1 + 0.20*designation + 0.15*classif`.
- Clean case: empty anomalies expected; any flag drops the 0.35 term and tanks
  precision. 705/1000 are clean, so over-flagging is the single biggest risk.
