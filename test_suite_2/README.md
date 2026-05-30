# Provenance `/verify` — Test Suite (drop-in)

A self-contained `pytest` + `pytest-bdd` suite for the Canadian-supply-chain
provenance verifier. Grounded in the real `training_corpus.jsonl` (1,000 labelled
cases): every attack family, anomaly type, threshold, and score floor was
**measured from the data**, not assumed.

Runs two ways:
- **Offline** (default): grades the bundled reference verifier — no server needed.
- **Live**: grades YOUR `/verify` backend over HTTP.

## Layout

```
provenance-verify-tests/
  conftest.py            bootstraps sys.path + fixtures (backend_url, corpus, etc.)
  pytest.ini             markers + config
  requirements.txt       pytest, pytest-bdd, cryptography, requests
  Makefile               make test | bdd | oracle | t4 | live
  run_tests.sh           ./run_tests.sh [offline|live]
  CORPUS_GROUND_TRUTH.md the measured analysis (families/types/signals)
  data/
    training_corpus.jsonl   the 1,000 labelled cases
  provtests/             importable library
    ground_truth.py         17 families, 11 types, rules, constants
    corpus.py               loader + genuine-distribution builder
    canonical.py            byte-exact canonical JSON + Ed25519
    scoring.py              the harness per-case formula (from self_test.py)
    reference_verifier.py   complete oracle: pct+designation+12 detectors+T4 (~95.4%)
    t4_detector.py          calibrated statistical detector (0 clean FPs)
    mutators.py             synthetic chains injecting each real family
    reference_logic.py      spec pure-functions (unit-test oracle)
    builders.py             attestation builders
    adapters.py             <-- wire to YOUR code / backend here
  tests/                 pytest files
    test_corpus_ground_truth.py   corpus structure == assumptions
    test_reference_oracle.py      oracle reproduces labels at measured floors
    test_t4_detector.py           T4 F1 floors + zero clean leakage
    test_canonical.py             byte rules, hashing, signing
    test_percentage.py            percentage maths + boundaries
    test_designation.py           designation rules + inclusive thresholds
    test_mass_balance.py          aggregate over-consumption, leftover legal
    test_verify_contract.py       /verify HTTP contract (LIVE)
    test_corpus_regression.py     replay corpus through harness scorer (LIVE)
    test_groundtruth_bdd.py       48 BDD scenarios bound to the verifier
  features/
    verify_groundtruth.feature    corpus-grounded BDD (primary)
    verify_complete.feature       spec-level BDD (reference)
```

## Quick start

```bash
cd provenance-verify-tests
pip install -r requirements.txt        # or: make install

# Offline: grade the bundled reference verifier (no server)
pytest -m "not live"                    # or: make test
#   -> ~95.4% self-test, 100% on clean, all TDD/BDD green

# Live: grade YOUR backend
docker compose up -d                    # your stack, /verify on :8000
BACKEND_URL=http://localhost:8000/verify pytest -m live   # or: make live
```

`./run_tests.sh` installs deps if missing and runs the offline suite;
`./run_tests.sh live` runs the live set against `$BACKEND_URL`.

## Testing YOUR backend two ways

1. **Over HTTP (recommended).** Set `BACKEND_URL` (or `--backend-url`). The live
   tests (`test_verify_contract.py`, `test_corpus_regression.py`) POST chains to
   your `/verify` and grade responses with the exact harness formula.
2. **In-process.** Edit `provtests/adapters.py` to point `verify_chain`,
   `compute_percentage`, `compute_designation`, `detect_hard_rule_anomalies` at
   your Python implementation; the corpus-grounded TDD/BDD tests then grade your
   functions directly (no server).

## Verified numbers (measured from the corpus)

Reference verifier self-test over 1,000 cases: **95.4% overall, 100% on the 705
clean cases (zero over-flagging).** Hard-rule detection F1 is 1.00 on 8 families
(timestamp_inversion, mass_balance, dangling_parent, parent_hash_mismatch,
unit_mismatch, replay_within_chain, unknown_supplier, cost_anomaly), 0.94 on
circular, 0.82 on transformation_implausible. T4: origin 0.97, timing 0.88,
labour 0.70, with 0 clean false positives.

## Two documented gaps (and how to close them)

1. **`signature_corrupt` / `tamper_no_resign`** need `supplier_public_keys.json`
   from the full kit (not bundled here). Drop it in `data/` and pass to
   `verify_chain(..., public_keys=...)`; the hook exists. Then both reach ~1.0.
2. **`t4_cost_outlier`** is left unsolved by rule on purpose (a per-action
   z-score earns ~0.10 F1 while flagging ~145 clean attestations — a bad F1
   trade). Close it with a quantile/heavy-tailed cost model conditional on
   action_type; keep clean FPs ~0. See the COST note in `t4_detector.py`.

Markers: `corpus` (uses bundled data), `live` (needs a backend), `slow`,
`golden`. Tests skip cleanly when an optional dependency is absent.
