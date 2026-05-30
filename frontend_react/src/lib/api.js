// Same-origin in production (FastAPI serves the SPA). Dev uses Vite proxy.
const BASE = import.meta.env.VITE_API_BASE || '';

export async function verifyChain(submission) {
  const r = await fetch(`${BASE}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  });
  if (!r.ok) throw new Error(`verify failed: ${r.status}`);
  return r.json();
}

export async function publishProduct(submission) {
  const r = await fetch(`${BASE}/api/products`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  });
  if (!r.ok) throw new Error(`publish failed: ${r.status}`);
  return r.json(); // { product_id, name, qr_url }
}

export async function resolveProduct(productId) {
  const r = await fetch(`${BASE}/api/products/${encodeURIComponent(productId)}`);
  if (r.status === 404) throw new Error('Product not found. Has it been published?');
  if (!r.ok) throw new Error(`lookup failed: ${r.status}`);
  return r.json(); // { product_id, name, published_by, chain }
}

export async function listProducts() {
  const r = await fetch(`${BASE}/api/products`);
  if (!r.ok) throw new Error(`list failed: ${r.status}`);
  return r.json(); // [{ product_id, name, published_by, created_at }]
}

export const qrUrl = (productId) => `${BASE}/api/qr/${encodeURIComponent(productId)}`;
