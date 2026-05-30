# Provenance verifier test suite v4

This version keeps the heavy pytest matrix from v2/v3 and adds a **packed BDD feature file**:

```text
features/provenance_verifier_packed.feature
```

It is intentionally one large Gherkin contract that maps to the behaviour described in the hackathon docs:

- `/verify` response contract
- official worked example
- unordered attestation DAGs
- direct-cost Canadian percentage calculation
- `made_in_canada` and `product_of_canada` threshold boundaries
- last substantial transformation requirement
- no-substantial-transformation designation rule
- clean unanchored chains are valid because the anchor registry is not exhaustive
- signature verification using the claimed supplier key
- unknown supplier detection
- parent content-hash mismatch detection
- dangling parent detection
- cycle detection
- replay / duplicate attestation detection
- timestamp inversion detection
- unit mismatch detection
- mass-balance overconsumption detection
- bad numeric values
- transformation plausibility checks
- cost plausibility checks
- pairwise and curated triple combined attacks

## Install

From your verifier repo root:

```bash
pip install pytest pytest-bdd requests fastapi
```

Point the suite at your implementation using one of:

```bash
export PROVENANCE_VERIFY_URL=http://127.0.0.1:8000/verify
# or
export PROVENANCE_VERIFY_FUNCTION=verifier:verify_payload
# or
export PROVENANCE_APP_MODULE=app.main:app
```

Make sure the original hackathon repo files are available. If needed:

```bash
export PROVENANCE_REPO_ROOT=/path/to/provenance-hackathon-main
```

## Run

```bash
pytest -q
```

Only the packed BDD tests:

```bash
pytest -q tests/test_gherkin_steps.py
```

Heavy combination matrix:

```bash
FULL_COMBINATION_MATRIX=1 pytest -q tests/test_combination_matrix.py
```

Capped powerset matrix:

```bash
FULL_COMBINATION_MATRIX=1 MAX_COMBINATION_SIZE=3 pytest -q tests/test_combination_matrix.py
```

## Important note

No finite BDD file can literally cover every possible malformed JSON object, every numeric value, or every held-out statistical attack. This suite covers every explicit rule family and anomaly angle named in the codebase markdown/specs, then uses parametrized pytest to cover broad combinations.
