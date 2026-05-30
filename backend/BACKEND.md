# AEGIS Backend — Complete Reference

The verification backend for **Cryptographic Provenance for Canadian Supply
Chains** (Ottawa Defence Hackathon). It does two jobs in one FastAPI container on
port **8000**:

1. **`POST /verify`** — the *only* automatically-graded endpoint. Stateless,
   DB-free, byte-exact with the scoring harness. Given an attestation chain it
   returns the Canadian-content percentage, designation, chain validity, and the
   integrity anomalies it found.
2. **A demo application API** (`/api/*`) backed by PostgreSQL — supplier
   registration, attestation issuing with cryptographic integrity enforcement,
   product publishing, QR generation, and chain resolution. This powers the
   supplier and purchaser UIs (web `frontend_react` and the `mobile/` Flutter
   app); it is **not** graded but drives the live demo.

The same container also serves the built React SPA from `backend/static/`.

---

## 1. Current score

`python verify.py` grades the engine in-process against the 1,000-case
`training_corpus.jsonl` using the official harness formula:

```
overall: 98.6%  (1000 cases)

hard (rule-based)   F1 = 1.000   (215/0/0  tp/fp/fn)   ← every structural/crypto attack
t4 (statistical)    F1 = 0.954   (114/1/10)            ← learned soft outliers
all non-clean       F1 = 0.984
clean over-flagging: 10/705 cases (1.4%)
```

Per-category: all hard attack families score 100%; the remaining gap is in the
statistical "t4" families (`t4_labour_outlier` 78.6%, `t4_cost_outlier` 82.4%),
which are legal on every rule and only anomalous relative to the corpus
distribution.

---

## 2. Architecture at a glance

```
                       POST /verify  (graded, stateless)
  client ───────────────────────────────────────────────► verify.verify_chain()
                                                              │  pure function, no DB
                                                              ▼
                                              vendor/reference_lib  (byte-exact crypto)
                                              data/*.json           (keys, anchors, stats)

                       /api/*  (demo app, stateful)
  UIs   ───────────────────────────────────────────────► FastAPI routes (main.py)
                                                              │
                          AttestationIntegrityMiddleware ─────┤  (enforces sigs on /api/attest)
                                                              ▼
                                                          PostgreSQL (db.py schema)
```

Two verification paths exist deliberately:

| | `POST /verify` (graded) | `GET /api/product/{id}` (demo) |
|---|---|---|
| State | Stateless; chain is in the request | Reads chain from DB, traverses by stored edges |
| Crypto | `vendor/reference_lib` (harness-exact) | `crypto.py` (hex-encoded, app convention) |
| Purpose | Leaderboard score | Rich purchaser report (cost breakdown, supplier chain) |
| Returns | Spec contract (5 fields) | Extended report (breakdown, dag_valid, chain_length…) |

> The graded engine never touches the database, so harness runs are deterministic
> and independent of demo data.

---

## 3. The scored engine — `verify.py`

`verify_chain(submission: dict) -> dict` is a pure function. Pipeline:

1. **Sanitize input** — tolerate a non-list `attestations`, drop any entry that
   isn't a dict, so one malformed attestation can never 500 the request.
2. **Build the DAG** — dedup by `attestation_id` (first occurrence wins) into
   `by_id`; the chain is reconstructed from each node's `parents`.
3. **Compute content & designation** — `compute_content()` (see §4).
4. **Detect hard anomalies** — `detect_anomalies()` (see §5). `chain_valid` is
   `True` iff zero *hard* anomalies fired.
5. **Detect statistical outliers** — `detect_outliers()` runs **only when the
   chain is otherwise clean** (hard and soft are mutually exclusive in the
   corpus; gating protects precision).

### Response contract

```json
{
  "product_attestation_id": "att-...",
  "canadian_content_percentage": 58.4,
  "designation": "made_in_canada",
  "chain_valid": false,
  "anomalies": [
    {"type": "mass_balance_violation", "attestation_id": "att-...", "details": "..."}
  ]
}
```

---

## 4. Canadian content & designation (`compute_content`)

Implements `spec/computation.md` exactly:

```
direct cost of an attestation = material_cad + labour_cost_cad      (labour_hours is NOT a cost)
percentage = Σ(direct cost of CA attestations) / Σ(direct cost of all) × 100
```

- The sum iterates the **submitted list** (a replay duplicate is counted as
  sent), matching the labeler.
- `performed_in_country` decides Canadian-ness **per attestation**, independent of
  the supplier's registered country. CA codes accepted: `CA`, `CAN`, `CANADA`.
- Percentage is clamped to `[0, 100]` so tampered negative costs can't push it
  out of range.

**Substantial transformation** = `action_type ∈ {component_manufacture,
subassembly, final_integration}` **and** `labour_hours ≥ 4`. The **last**
substantial transformation is found by BFS over `parents` from the product leaf —
the qualifying node closest to the leaf wins.

```
if no substantial transformation OR last one not performed in CA → none
elif percentage ≥ 98 → product_of_canada
elif percentage ≥ 51 → made_in_canada
else                 → none
```

---

## 5. Anomaly taxonomy

`anomalies[].type` is a free-form label; the harness scores detection by
attestation with F1 (over-flagging hurts). AEGIS uses precise, recognizable type
strings for extra credit.

### Hard anomalies — invalidate the chain (`chain_valid = false`)

`HARD_TYPES` in `verify.py`:

| Type | Fires when |
|---|---|
| `signature_invalid` | Ed25519 signature doesn't verify against the supplier's registered key |
| `signature_unknown_supplier` | `supplier_id` not in the public-key registry |
| `parent_hash_mismatch` | a parent link's `content_hash` ≠ the parent's real canonical hash |
| `mass_balance_violation` | a node's children consume more than it produced (`Σ quantity_consumed > quantity_produced`) |
| `circular_reference` | a cycle exists in the parent graph (attributed to the back-edge target) |
| `dangling_parent` | a referenced parent id is absent from the submission |
| `timestamp_inversion` | a child's timestamp precedes its parent's |
| `unit_mismatch` | a child consumes in a unit ≠ the parent's `output.unit` |
| `replay_within_chain` | the same `attestation_id` appears more than once |
| `replay_cross_chain` | an anchored attestation is submitted under a different product than it's anchored to |
| `anchor_mismatch` | an anchored attestation's content hash differs from the published anchor value |
| `cost_anomaly` | negative numeric value, labour rate > 180 CAD/hr, or material cost > 100k CAD |
| `transformation_implausible` | a transform with no parents, a raw material *with* parents, or an unknown `action_type` |

> **Key insight (threat model):** all private keys ship in the kit, so an attacker
> can produce a correctly-signed *lie*. A valid signature only proves the bytes
> weren't garbled. Most hard checks above test **internal consistency and physical
> plausibility**, not signatures — that's where forgery without key theft is caught
> (e.g. relabel foreign work as Canadian → the unmodified signature/hash no longer
> matches → `signature_invalid` + `parent_hash_mismatch`).

### Statistical outliers — soft, learned (`type: statistical_outlier`)

Run only on otherwise-clean chains. Each is legal on every rule but anomalous vs
the genuine corpus distribution (`data/stats.json`):

- **Timing** — `timestamp` time-of-day ≠ the canonical value for that action
  (`09:00:00Z` for raw supply, `14:30:00Z` for transforms). Zero false positives
  on the clean corpus.
- **Origin** — a `raw_material_supply` claims `CA` from a supplier that is
  almost always foreign (CA share < 5% over ≥ 5 observations).
- **Labour-hours** — robust z-score of `labour_hours` vs the per-action genuine
  baseline (median + MAD), threshold `HOURS_Z = 2.6`.
- **Labour-rate** — robust z-score of `labour_cost_cad / labour_hours` vs the
  per-action baseline, threshold `RATE_Z = 2.8`.

Robust z = `(value − median) / (1.4826 × MAD)`. Per-action baselines are used
because genuine rate bands overlap across action types, so a flat ceiling can't
separate the attack band (≈97–117 CAD/hr) from genuine work. Thresholds were
calibrated against the corpus harness score (`analysis/calibrate.py`) and can be
overridden via `AEGIS_RATE_Z` / `AEGIS_HOURS_Z` env vars for sweeps.

---

## 6. Canonical serialization & crypto

Signatures and content hashes only match across implementations if everyone
serializes identically. Two layers exist:

- **`vendor/reference_lib/`** — the shipped reference library, vendored so the
  graded `/verify` is **byte-exact** with the harness. `canonical.content_hash`
  (SHA-256 of the canonical form, signature excluded) and
  `crypto.verify_attestation` are used by `verify.py`. Rules: JSON with keys
  sorted at every level, compact (no whitespace), UTF-8; the `signature` field is
  excluded from signed/hashed bytes; whole numbers serialize as integers
  (`1`, not `1.0`); no NaN/Infinity.
- **`crypto.py`** — the demo app's own Ed25519 helpers (hex-encoded keys/sigs,
  `canonical_json` with `sort_keys + compact separators`). Used by the stateful
  `/api/*` routes and the integrity middleware.

`content_addressed_id(payload)` = SHA-256 of the canonical JSON, so any mutation
yields a different id (content-addressed attestations).

---

## 7. The demo application API (`main.py`, stateful)

Backed by PostgreSQL (`db.py`). Routes:

**Suppliers**
- `GET  /api/suppliers` — list registered suppliers
- `POST /api/suppliers` — register `{supplier_id, name, country, province, public_key_hex}`
- `POST /api/wallet/verify` — prove possession of a private key: the client signs
  a known payload, the server verifies it against the registered public key
  (client-side Ed25519 wallet auth)

**Attestations**
- `POST /api/attest` — issue a signed attestation. **Guarded by
  `AttestationIntegrityMiddleware`** (see §8). Stores the *raw wire payload* (not
  a Pydantic re-dump) so whole-number coercion can't break signatures. Computes a
  content-addressed id and records `sig_valid`.
- `GET  /api/attest/{id}` — fetch one
- `GET  /api/attestations` — recent list
- `GET  /api/verify/{id}` — signature/known-signer check for a single stored attestation

**Provenance & products**
- `GET  /api/product/{id}` — resolve a chain from the DB and return a **rich
  report**: supplier chain, cost breakdown, percentage, designation,
  `last_transformation_in_canada`, anomalies, `dag_valid`, `chain_length`. Uses
  `collect_chain_graceful` so partial chains (missing refs, cycles) still produce
  a meaningful report with structural anomalies accumulated.
- `POST /api/products` — a supplier **publishes** a verified chain under its leaf
  id (upsert into `published_products`)
- `GET  /api/products` / `GET /api/products/{id}` — list / resolve published products
- `GET  /api/qr/{id}` — PNG QR encoding the purchaser deep-link
  `{base_url}/purchaser?pid={id}` (what the mobile/web purchaser scans)

**Ops**
- `POST /api/seed`, `POST /api/seed/edge-cases` — load demo data / planted attacks
- `GET  /health` — liveness
- `GET  /{path}` — SPA fallback (serves the React build; API routes take precedence)

### Demo scan flow (what the UIs do)

```
QR ──► extract pid ──► GET /api/products/{pid}  (resolve chain)
                  └──► POST /verify  (graded verdict)  ──► render report
```

---

## 8. Integrity middleware (`middleware.py`)

`AttestationIntegrityMiddleware` intercepts `POST /api/attest` *before* routing
and runs three pre-flight checks:

1. **Envelope coherence** — `signer_id` must equal `payload.supplier_id`
2. **Registry lookup** — signer must be a registered supplier
3. **Signature verify** — Ed25519 over canonical JSON must be valid

Any failure raises `IntegrityViolationError` → HTTP **422** with a structured
body (`exceptions.py`). The original request body is re-injected into the ASGI
receive channel so the downstream handler reads an intact request. Middleware
(not a `Depends()`) is used so the check is unconditional and cannot be bypassed
by hitting a different handler. CORS is added first so preflight `OPTIONS` pass
through.

---

## 9. Data assets

| Path | Contents |
|---|---|
| `data/supplier_public_keys.json` | `supplier_id → Ed25519 public key` (graded-path registry) |
| `data/anchor_registry.json` | published anchors: `attestation_id → {content_hash, product_id}` (non-exhaustive; absence is *not* an anomaly) |
| `data/stats.json` | corpus-learned baselines: per-supplier country counts, per-action robust labour-hours/rate medians+MAD, clean maxima |

`stats.json` is produced from `training_corpus.jsonl` by the analysis scripts
(`analysis/`). It encodes "how genuine chains look", which is what the statistical
detectors compare against.

---

## 10. Running

### Docker Compose (from repo root)

```bash
docker compose up --build      # backend on :8000 + postgres
```

Brings up Postgres and the FastAPI backend; the backend serves `/verify`,
`/api/*`, and the React SPA on one port.

### Grade against the training corpus

```bash
# in-process scorecard (fast, no server)
cd backend && python verify.py [path/to/training_corpus.jsonl]

# official harness against a running server
python self_test.py http://localhost:8000/verify
```

### Smoke-test `/verify`

```bash
curl -s -X POST http://localhost:8000/verify \
  -H 'Content-Type: application/json' \
  --data @../worked-example/recovery_drone_chain.json
# → 58.4%, made_in_canada, chain_valid=true, anomalies=[]
```

### Container

`Dockerfile`: `python:3.12-slim`, installs `requirements.txt`, runs
`uvicorn main:app --host 0.0.0.0 --port 8000 --reload`. `DATABASE_URL` is supplied
by compose. (`Procfile` / `railway.json` exist for a hosted deploy; see
`aegis_deploy/` for the no-Postgres SQLite/WSGI shim used on shared hosting.)

Dependencies: `fastapi`, `uvicorn[standard]`, `asyncpg`, `cryptography`,
`pydantic`, `qrcode[pil]`, `Pillow`.

---

## 11. File map

| File | Role |
|---|---|
| `verify.py` | **The graded engine** — stateless `verify_chain` + self-scorecard |
| `vendor/reference_lib/` | Byte-exact canonical serialization + Ed25519 (harness-matched) |
| `data/*.json` | Keys, anchors, corpus-learned stats for the graded path |
| `main.py` | FastAPI app: all routes, startup, SPA mount |
| `crypto.py` | Demo-app Ed25519 helpers + content-addressed ids |
| `middleware.py` | Unconditional signature/integrity enforcement on `/api/attest` |
| `exceptions.py` | `IntegrityViolationError` → structured 422 |
| `models.py` | Pydantic request/response models |
| `db.py` | asyncpg pool + schema (`suppliers`, `attestations`, `attestation_inputs`, `published_products`) |
| `graph.py` | DB-backed DAG traversal (`collect_chain`, `collect_chain_graceful`) |
| `canadian_content.py` | Content/designation for the DB-backed report path |
| `anomaly.py` | Anomaly checks for the DB-backed report path |
| `registry.py` | Supplier registry CRUD |
| `ledger.py` | Anchor/ledger helpers |
| `seed.py`, `seed_edge_cases.py` | Demo data and planted-attack seeders |
