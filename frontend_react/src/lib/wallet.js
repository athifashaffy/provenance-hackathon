/* AEGIS browser crypto, byte-exact with reference_lib/canonical.py + crypto.py.
 * Canonical JSON: sorted keys at every level, compact, signature excluded,
 * whole numbers as integers, non-whole with no trailing zeros, UTF-8.
 * Ed25519 keys/signatures are base64 (raw 32-byte key, 64-byte sig). */

function fmtNum(n) {
  if (typeof n === 'boolean') return n ? 'true' : 'false';
  if (Number.isInteger(n)) return String(n);
  if (!isFinite(n)) throw new Error('non-finite number in canonical form');
  const s = String(n);
  if (s.includes('e') || s.includes('E')) throw new Error('scientific notation not supported');
  return s;
}
function esc(s) {
  let out = '"';
  for (const ch of s) {
    const c = ch.charCodeAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (ch === '\n') out += '\\n';
    else if (ch === '\r') out += '\\r';
    else if (ch === '\t') out += '\\t';
    else if (ch === '\b') out += '\\b';
    else if (ch === '\f') out += '\\f';
    else if (c < 0x20) out += '\\u' + c.toString(16).padStart(4, '0');
    else out += ch;
  }
  return out + '"';
}
function ser(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return fmtNum(v);
  if (typeof v === 'string') return esc(v);
  if (Array.isArray(v)) return '[' + v.map(ser).join(',') + ']';
  return '{' + Object.keys(v).sort().map((k) => esc(k) + ':' + ser(v[k])).join(',') + '}';
}
function canonicalBytes(obj, excludeSig) {
  let o = obj;
  if (excludeSig && o && typeof o === 'object' && !Array.isArray(o)) {
    o = {}; for (const k of Object.keys(obj)) if (k !== 'signature') o[k] = obj[k];
  }
  return new TextEncoder().encode(ser(o));
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function bytesToB64(bytes) {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
const toHex = (b) => Array.from(b).map((x) => x.toString(16).padStart(2, '0')).join('');

const PKCS8_PREFIX = new Uint8Array([
  0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06,
  0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);

async function importPriv(privB64, extractable = false) {
  const raw = b64ToBytes(privB64);
  const pkcs8 = new Uint8Array(PKCS8_PREFIX.length + raw.length);
  pkcs8.set(PKCS8_PREFIX); pkcs8.set(raw, PKCS8_PREFIX.length);
  return crypto.subtle.importKey('pkcs8', pkcs8.buffer, { name: 'Ed25519' }, extractable, ['sign']);
}
async function importPub(pubB64) {
  return crypto.subtle.importKey('raw', b64ToBytes(pubB64).buffer, { name: 'Ed25519' }, false, ['verify']);
}

export async function sign(att, privB64) {
  const key = await importPriv(privB64);
  const sig = await crypto.subtle.sign({ name: 'Ed25519' }, key, canonicalBytes(att, true));
  const copy = JSON.parse(JSON.stringify(att));
  copy.signature = { algorithm: 'ed25519', value: bytesToB64(new Uint8Array(sig)) };
  return copy;
}
export async function verify(att, pubB64) {
  try {
    const sf = att.signature;
    if (!sf || sf.algorithm !== 'ed25519' || !sf.value) return false;
    const key = await importPub(pubB64);
    return crypto.subtle.verify({ name: 'Ed25519' }, key, b64ToBytes(sf.value), canonicalBytes(att, true));
  } catch { return false; }
}
export async function contentHash(att) {
  const d = await crypto.subtle.digest('SHA-256', canonicalBytes(att, true));
  return toHex(new Uint8Array(d));
}
export async function pubFromPriv(privB64) {
  const kp = await importPriv(privB64, true);
  const jwk = await crypto.subtle.exportKey('jwk', kp);
  let x = jwk.x.replace(/-/g, '+').replace(/_/g, '/');
  while (x.length % 4) x += '=';
  return x;
}
export const canonicalString = (o) => new TextDecoder().decode(canonicalBytes(o, true));

// Deterministic 6-digit 2FA code derived by signing a fixed challenge with the
// wallet key, then folding the signature into 6 digits. Same key => same code,
// so the demo can show the expected code while still proving key possession.
export async function twoFactorCode(privB64) {
  const key = await importPriv(privB64);
  const msg = new TextEncoder().encode('aegis-2fa-challenge-v1');
  const sig = new Uint8Array(await crypto.subtle.sign({ name: 'Ed25519' }, key, msg));
  let n = 0;
  for (let i = 0; i < 6; i++) n = (n * 256 + sig[i]) >>> 0;
  return String(n % 1000000).padStart(6, '0');
}
