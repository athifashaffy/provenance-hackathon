"""
Supply Chain Provenance — FastAPI backend
TAN Hackathon: Verified Canadian Supply Chains
"""

import json
import io
import os
import asyncpg
from graph import _parse_att as _pa
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import qrcode

from db import get_pool, init_schema
from models import AttestationSubmit, SupplierCreate, VerificationResult, ProvenanceReport
from crypto import content_addressed_id, verify_signature
from registry import get_supplier, list_suppliers, register_supplier
from graph import collect_chain, collect_chain_graceful
from canadian_content import compute_content
from anomaly import run_all_checks
from exceptions import IntegrityViolationError
from middleware import AttestationIntegrityMiddleware
from verify import verify_chain

app = FastAPI(title="TAN Supply Chain Provenance", version="1.0.0")

# ── Middleware (order matters: CORS first, then integrity check) ───────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cryptographic integrity enforcement on POST /api/attest.
# Must be added AFTER CORSMiddleware so CORS preflight OPTIONS pass through.
app.add_middleware(AttestationIntegrityMiddleware)


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(IntegrityViolationError)
async def integrity_violation_handler(request: Request, exc: IntegrityViolationError):
    """Convert IntegrityViolationError → HTTP 422 with structured body."""
    return JSONResponse(exc.to_dict(), status_code=422)


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    pool = await get_pool()
    # Store on app.state so the integrity middleware can access it
    app.state.pool = pool
    await init_schema(pool)


# ── Dependency ────────────────────────────────────────────────────────────────

async def db() -> asyncpg.Pool:
    return await get_pool()


# ── Suppliers ─────────────────────────────────────────────────────────────────

@app.get("/api/suppliers")
async def api_list_suppliers(pool=Depends(db)):
    return await list_suppliers(pool)


@app.post("/api/suppliers", status_code=201)
async def api_register_supplier(body: SupplierCreate, pool=Depends(db)):
    return await register_supplier(
        pool,
        supplier_id=body.supplier_id,
        name=body.name,
        country=body.country,
        province=body.province,
        public_key_hex=body.public_key_hex,
    )


# ── Wallet Auth (verify key pair) ─────────────────────────────────────────────

@app.post("/api/wallet/verify")
async def api_wallet_verify(body: dict, pool=Depends(db)):
    """Verify that a private key matches a supplier's registered public key.
    Accepts {supplier_id, proof_signature, proof_payload}.
    The frontend signs a known payload dict with the private key and we verify
    the signature against the registered public key."""
    supplier_id = body.get("supplier_id", "")
    proof_sig = body.get("proof_signature", "")
    proof_payload = body.get("proof_payload")

    if not supplier_id or not proof_sig or not proof_payload:
        raise HTTPException(400, "Missing supplier_id, proof_signature, or proof_payload")

    supplier = await get_supplier(pool, supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    valid = verify_signature(
        proof_payload, proof_sig, supplier["public_key_hex"]
    )
    if not valid:
        raise HTTPException(401, "Key verification failed")
    return {"verified": True, "supplier_id": supplier_id}


# ── Attestations ──────────────────────────────────────────────────────────────

@app.post("/api/attest", status_code=201)
async def api_attest(request: Request, body: AttestationSubmit, pool=Depends(db)):
    # Use the wire-format payload dict (stored by AttestationIntegrityMiddleware)
    # rather than body.payload.model_dump(). Pydantic coerces int→float (e.g.
    # cost_cad:1 → 1.0), which changes the canonical JSON and breaks signature
    # verification and content-addressed IDs for whole-number values.
    payload_dict: dict = request.scope.get("_raw_payload") or body.payload.model_dump()

    # Compute content-addressed ID from the exact bytes that were signed
    att_id = content_addressed_id(payload_dict)

    # Signature validity — middleware already verified this for known signers,
    # but we re-run here to populate sig_valid in the DB record.
    supplier = await get_supplier(pool, body.signer_id)
    sig_valid = (
        verify_signature(payload_dict, body.signature, supplier["public_key_hex"])
        if supplier else False
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO attestations (id, payload, signature, signer_id, sig_valid)
            VALUES ($1, $2::jsonb, $3, $4, $5)
            ON CONFLICT (id) DO NOTHING
        """, att_id, json.dumps(payload_dict), body.signature, body.signer_id, sig_valid)

        # Store input edges
        for input_id in (body.payload.inputs or []):
            await conn.execute("""
                INSERT INTO attestation_inputs (attestation_id, input_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
            """, att_id, input_id)

    return {
        "attestation_id": att_id,
        "signature_valid": sig_valid,
        "message": "Attestation recorded" + ("" if sig_valid else " (WARNING: invalid signature)"),
    }


@app.get("/api/attest/{att_id}")
async def api_get_attestation(att_id: str, pool=Depends(db)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM attestations WHERE id = $1", att_id)
    if row is None:
        raise HTTPException(404, "Attestation not found")
    return _pa(dict(row))


@app.get("/api/attestations")
async def api_list_attestations(pool=Depends(db)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, signer_id, sig_valid, created_at, payload->>'product_name' AS product_name "
            "FROM attestations ORDER BY created_at DESC LIMIT 100"
        )
    return [dict(r) for r in rows]


# ── Verification ──────────────────────────────────────────────────────────────

@app.get("/api/verify/{att_id}", response_model=VerificationResult)
async def api_verify(att_id: str, pool=Depends(db)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM attestations WHERE id = $1", att_id)
    if row is None:
        raise HTTPException(404, "Attestation not found")

    record = _pa(dict(row))
    payload = record["payload"]
    signer_id = record["signer_id"]
    signature = record["signature"]

    supplier = await get_supplier(pool, signer_id)
    known_signer = supplier is not None
    valid_sig = (
        verify_signature(payload, signature, supplier["public_key_hex"])
        if known_signer else False
    )

    anomalies_list = []
    if not known_signer:
        anomalies_list.append(f"Unknown signer: {signer_id}")
    if not valid_sig:
        anomalies_list.append("Invalid Ed25519 signature")

    return VerificationResult(
        attestation_id=att_id,
        valid_signature=valid_sig,
        known_signer=known_signer,
        payload=payload,
        anomalies=anomalies_list,
    )


# ── Provenance Report ─────────────────────────────────────────────────────────

@app.get("/api/product/{att_id}")
async def api_product(att_id: str, pool=Depends(db)):
    # 1. Traverse DAG — graceful mode continues past missing references rather
    #    than aborting, so partial chains still produce a meaningful report.
    #    Structural anomalies (missing refs, cycles) are accumulated alongside
    #    whatever portion of the chain was reachable.
    chain_nodes, structural_anomalies = await collect_chain_graceful(pool, att_id)

    dag_valid = len(structural_anomalies) == 0

    if not chain_nodes:
        raise HTTPException(404, "Attestation not found")

    # 2. Compute Canadian content
    content = compute_content(chain_nodes)

    # 3. Run anomaly checks
    all_anomalies = await run_all_checks(chain_nodes, pool, structural_anomalies)

    # 4. Build supplier chain summary
    supplier_chain = []
    for node in chain_nodes:
        p = node["payload"]
        supplier_chain.append({
            "attestation_id": node["id"],
            "product_name": p.get("product_name", ""),
            "supplier_id": node["signer_id"],
            "location": p.get("location", {}),
            "inputs": p.get("inputs", []),
            "sig_valid": node["sig_valid"],
        })

    root_payload = chain_nodes[0]["payload"] if chain_nodes else {}

    return {
        "product_attestation_id": att_id,
        "product_name": root_payload.get("product_name", "Unknown"),
        "supplier_chain": supplier_chain,
        "total_cost_cad": content["total_cost_cad"],
        "canadian_cost_cad": content["canadian_cost_cad"],
        "canadian_content_pct": content["canadian_content_pct"],
        "designation": content["designation"],
        "last_transformation_in_canada": content["last_transformation_in_canada"],
        "cost_breakdown": content["cost_breakdown"],
        "anomalies": all_anomalies,
        "dag_valid": dag_valid,
        "chain_length": len(chain_nodes),
    }


# ── Published products: publish · resolve · QR ────────────────────────────────

@app.post("/api/products")
async def api_publish_product(request: Request, pool=Depends(db)):
    """A supplier publishes a verified chain under its product (leaf) id.
    Body: { product_attestation_id, attestations: [...] }."""
    body = await request.json()
    pid = body.get("product_attestation_id")
    atts = body.get("attestations") or []
    if not pid or not atts:
        raise HTTPException(400, "product_attestation_id and attestations are required")
    leaf = next((a for a in atts if a.get("attestation_id") == pid), None)
    name = (leaf or {}).get("output", {}).get("name") or "Product"
    published_by = (leaf or {}).get("supplier_id")
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO published_products (product_id, name, chain, published_by)
               VALUES ($1, $2, $3::jsonb, $4)
               ON CONFLICT (product_id) DO UPDATE
               SET chain = EXCLUDED.chain, name = EXCLUDED.name, published_by = EXCLUDED.published_by""",
            pid, name, json.dumps(body), published_by,
        )
    return {"product_id": pid, "name": name, "qr_url": f"/api/qr/{pid}"}


@app.get("/api/products/{product_id}")
async def api_get_product(product_id: str, pool=Depends(db)):
    """Resolve a published product's full chain (what the purchaser scan loads)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT product_id, name, chain, published_by FROM published_products WHERE product_id = $1",
            product_id,
        )
    if row is None:
        raise HTTPException(404, "Product not found")
    chain = row["chain"]
    if isinstance(chain, str):
        chain = json.loads(chain)
    return {"product_id": row["product_id"], "name": row["name"],
            "published_by": row["published_by"], "chain": chain}


@app.get("/api/products")
async def api_list_products(pool=Depends(db)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT product_id, name, published_by, created_at FROM published_products ORDER BY created_at DESC LIMIT 100"
        )
    return [dict(r) for r in rows]


@app.get("/api/qr/{product_id}")
async def api_qr(product_id: str, request: Request):
    """QR encodes the purchaser deep-link that auto-resolves this product."""
    # same-origin: the SPA is served from this backend
    base = str(request.base_url).rstrip("/")
    url = f"{base}/purchaser?pid={product_id}"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1f3a8a", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# ── Seed ──────────────────────────────────────────────────────────────────────

@app.post("/api/seed")
async def api_seed(pool=Depends(db)):
    from seed import seed
    result = await seed(pool)
    return result


@app.post("/api/seed/edge-cases")
async def api_seed_edge_cases(pool=Depends(db)):
    from seed_edge_cases import seed_edge_cases
    result = await seed_edge_cases(pool)
    return result


# ── Scored verification endpoint (stateless, DB-free) ──────────────────────────

@app.post("/verify")
async def verify(request: Request):
    """Official challenge contract: accept a full attestation chain and return
    {product_attestation_id, canadian_content_percentage, designation,
     chain_valid, anomalies}. Stateless — does not touch the database."""
    submission = await request.json()
    return JSONResponse(verify_chain(submission))


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Static SPA (React/Vite build) ─────────────────────────────────────────────
# Mounted LAST so API routes above take precedence. Serves the built frontend and
# falls back to index.html for client-side routes (/supplier, /purchaser).
_STATIC = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = os.path.join(_STATIC, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_STATIC, "index.html"))
