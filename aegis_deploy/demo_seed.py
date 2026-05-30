"""Idempotent demo-product seeding for the hosted (Cloud Run) deployment.

Cloud Run storage is ephemeral: if the instance recycles, the SQLite DB resets.
To keep **printed QR codes** working across recycles, we re-publish a fixed set
of demo products — with STABLE product ids — on every startup. The ids never
change, so a QR printed once always resolves.

The chains live in `demo_products.json` (built from the verified local backend):
  * att-anchor-0012                         clean drone  -> verified, 58.4%, made_in_canada
  * att-tampered-drone-001                  foreign fabric relabeled CA -> chain_valid=false
  * att-f2cd93c3-...                         carbon fibre frame -> statistical_outlier
"""

import json
import os

_DEMO_PATH = os.path.join(os.path.dirname(__file__), "demo_products.json")


async def seed_demo_products(pool) -> int:
    """Upsert the fixed demo products into published_products. Returns the count."""
    try:
        with open(_DEMO_PATH) as f:
            products = json.load(f)
    except (OSError, ValueError):
        return 0

    n = 0
    for p in products:
        pid = p.get("product_id")
        if not pid:
            continue
        # `chain` is the full {product_attestation_id, attestations} body — the
        # exact shape /api/products/{id} returns and the purchaser app re-posts
        # to /verify.
        chain = p.get("chain") or {}
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO published_products (product_id, name, chain, published_by)
                   VALUES ($1, $2, $3::jsonb, $4)
                   ON CONFLICT (product_id) DO UPDATE
                   SET chain = EXCLUDED.chain, name = EXCLUDED.name,
                       published_by = EXCLUDED.published_by""",
                pid, p.get("name") or "Product", json.dumps(chain), p.get("published_by"),
            )
        n += 1
    return n
