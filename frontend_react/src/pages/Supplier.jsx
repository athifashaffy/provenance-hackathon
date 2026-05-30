import { useState, useEffect, useRef } from 'react';
import demo from '../demo-data.json';
import * as W from '../lib/wallet.js';
import { verifyChain, publishProduct, qrUrl, listProducts } from '../lib/api.js';
import Verdict from '../components/Verdict.jsx';
import { COUNTRIES } from '../lib/countries.js';

const ACTIONS = ['raw_material_supply', 'component_manufacture', 'subassembly', 'final_integration'];

export default function Supplier() {
  const [wallet, setWallet] = useState(null);
  const [loginId, setLoginId] = useState('');
  const [loginKey, setLoginKey] = useState('');
  const [loginErr, setLoginErr] = useState('');

  if (!wallet)
    return <Login {...{ loginId, setLoginId, loginKey, setLoginKey, loginErr, setLoginErr, onLogin: setWallet }} />;
  return <WalletView wallet={wallet} onLogout={() => setWallet(null)} />;
}

function Login({ loginId, setLoginId, loginKey, setLoginKey, loginErr, setLoginErr, onLogin }) {
  const [step, setStep] = useState('creds');         // creds | twofa
  const [pending, setPending] = useState(null);       // { id, key, pub, meta, expected }
  const [otp, setOtp] = useState('');
  const [busy, setBusy] = useState(false);

  // step 1: verify the key matches the registry, then move to 2FA
  async function submitCreds(id, key) {
    setLoginErr(''); setBusy(true);
    try {
      const regPub = demo.registry[id];
      if (!regPub) { setLoginErr('Supplier ID not found in the verified registry.'); return; }
      let derived;
      try { derived = await W.pubFromPriv(key); }
      catch { setLoginErr('Invalid key format (need a base64 Ed25519 private key).'); return; }
      if (derived !== regPub) { setLoginErr(`Key does not match the public key registered for ${id}.`); return; }
      const meta = demo.demoLogins.find((d) => d.supplier_id === id) || {};
      const expected = await W.twoFactorCode(key);     // deterministic device code
      setPending({ id, key, pub: regPub, meta, expected });
      setOtp(''); setStep('twofa');
    } finally { setBusy(false); }
  }

  // step 2: confirm 2FA, then unlock
  async function submitOtp(code) {
    setLoginErr('');
    if (code !== pending.expected) { setLoginErr('Incorrect authentication code.'); return; }
    onLogin({ supplier_id: pending.id, priv: pending.key, pub: pending.pub,
              name: pending.meta.name || pending.id, country: pending.meta.country || '' });
  }

  return (
    <div className="grid lg:grid-cols-2 gap-0 rounded-3xl overflow-hidden border border-aegis-line shadow-xl bg-white">
      {/* brand panel */}
      <div className="hidden lg:flex flex-col justify-between p-10 text-white"
           style={{ background: 'linear-gradient(150deg,#1f3a8a,#2f4fb0 60%,#16213e)' }}>
        <div className="flex items-center gap-2 font-display font-bold text-2xl tracking-wide">
          <span className="inline-grid place-items-center w-9 h-9 rounded-lg bg-white/15">⬡</span> AEGIS
        </div>
        <div>
          <div className="font-display font-bold text-3xl leading-tight">Enterprise<br/>Supplier Wallet</div>
          <p className="text-white/70 mt-3 text-sm leading-relaxed">
            Think of it as a hardware wallet for supply-chain provenance. Your private key never
            leaves this device; every attestation you issue is signed locally and cryptographically
            bound to your registered identity, verifiable by anyone without exposing your suppliers.
          </p>
        </div>
        <div className="text-white/40 text-xs">The Alpha Nova · Verified Canadian Supply Chains</div>
      </div>

      {/* form panel */}
      <div className="p-8 lg:p-10">
        {step === 'creds' && (
          <div className="space-y-5">
            <div>
              <div className="badge bg-aegis-blue/10 text-aegis-blue">Step 1 of 2 · Credentials</div>
              <h1 className="font-display font-bold text-2xl text-aegis-deep mt-2">Sign in to your wallet</h1>
            </div>
            <div>
              <label className="label">Supplier ID</label>
              <input className="input" value={loginId} onChange={(e) => setLoginId(e.target.value)} placeholder="sup-avss-corp" />
            </div>
            <div>
              <label className="label">Private signing key (base64)</label>
              <input className="input mono text-xs" type="password" value={loginKey}
                onChange={(e) => setLoginKey(e.target.value)} placeholder="base64 Ed25519 private key"
                onKeyDown={(e) => e.key === 'Enter' && submitCreds(loginId.trim(), loginKey.trim())} />
            </div>
            <button className="btn btn-primary w-full" disabled={busy}
              onClick={() => submitCreds(loginId.trim(), loginKey.trim())}>Continue →</button>
            {loginErr && <div className="text-aegis-red text-sm" data-testid="login-error">{loginErr}</div>}

            <div className="border-t border-aegis-line pt-4">
              <div className="label">Demo identities (one-click)</div>
              <div className="grid grid-cols-2 gap-2 mt-2">
                {demo.demoLogins.map((d) => (
                  <button key={d.supplier_id} data-testid="demo-login"
                    className="chip text-left justify-start py-2"
                    onClick={() => { setLoginId(d.supplier_id); setLoginKey(d.priv); submitCreds(d.supplier_id, d.priv); }}>
                    <span className="truncate">{d.name}<br/><span className="mono text-[0.6rem] text-aegis-muted">{d.supplier_id}</span></span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 'twofa' && (
          <div className="space-y-5">
            <div>
              <div className="badge bg-aegis-blue/10 text-aegis-blue">Step 2 of 2 · Two-factor</div>
              <h1 className="font-display font-bold text-2xl text-aegis-deep mt-2">Authenticate device</h1>
              <p className="text-aegis-muted text-sm mt-1">
                Enter the 6-digit code from your AEGIS authenticator for <b>{pending.meta.name || pending.id}</b>.
              </p>
            </div>
            <OtpBoxes value={otp} onChange={setOtp} onComplete={submitOtp} />
            <button className="btn btn-primary w-full" data-testid="verify-2fa" onClick={() => submitOtp(otp)}>Verify & unlock</button>
            {loginErr && <div className="text-aegis-red text-sm" data-testid="login-error">{loginErr}</div>}
            <div className="flex items-center justify-between text-sm">
              <button className="btn-ghost" onClick={() => { setStep('creds'); setLoginErr(''); }}>← Back</button>
              <div className="text-aegis-muted text-xs">
                Demo code: <span className="mono font-bold text-aegis-blue" data-testid="demo-otp">{pending.expected}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function OtpBoxes({ value, onChange, onComplete }) {
  const refs = useRef([]);
  const digits = value.padEnd(6, ' ').slice(0, 6).split('');
  function setAt(i, d) {
    const arr = value.padEnd(6, ' ').split('');
    arr[i] = d; const next = arr.join('').replace(/ /g, '');
    onChange(next);
    if (d && i < 5) refs.current[i + 1]?.focus();
    if (next.length === 6) onComplete(next);
  }
  return (
    <div className="flex gap-2" data-testid="otp">
      {digits.map((d, i) => (
        <input key={i} ref={(el) => (refs.current[i] = el)} className="otp-input" maxLength={1}
          inputMode="numeric" value={d.trim()}
          onChange={(e) => setAt(i, e.target.value.replace(/\D/g, '').slice(-1))}
          onKeyDown={(e) => { if (e.key === 'Backspace' && !d.trim() && i > 0) refs.current[i - 1]?.focus(); }}
          onPaste={(e) => { const p = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6); if (p) { onChange(p); if (p.length === 6) onComplete(p); } e.preventDefault(); }} />
      ))}
    </div>
  );
}

function WalletView({ wallet, onLogout }) {
  const [tab, setTab] = useState('dashboard');
  const [products, setProducts] = useState([]);
  const [loadingProducts, setLoadingProducts] = useState(false);

  async function refreshProducts() {
    setLoadingProducts(true);
    try {
      const all = await listProducts();
      setProducts(all.filter((p) => p.published_by === wallet.supplier_id));
    } catch { /* ignore */ }
    finally { setLoadingProducts(false); }
  }
  useEffect(() => { refreshProducts(); /* eslint-disable-next-line */ }, []);

  const [form, setForm] = useState({
    name: 'Carbon Fibre Frame', action: 'raw_material_supply', country: 'CA',
    qty: 1, unit: 'units', mat: 500, hrs: 0, lab: 0,
  });
  const [selectedParents, setSelectedParents] = useState([]); // attestation_ids of issued items
  const [issued, setIssued] = useState([]);   // {att, hash}
  const [signMsg, setSignMsg] = useState(null);
  const [result, setResult] = useState(null);
  const [verifiedChain, setVerifiedChain] = useState(null);
  const [published, setPublished] = useState(null); // { product_id, name }
  const [busy, setBusy] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const num = (v) => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

  // load the upstream parts of the demo drone so a real chain can be built fast
  async function seedDroneParts() {
    setBusy(true);
    const we = demo.samples.find((s) => s.id === 'clean').chain;
    const leafId = we.product_attestation_id;
    const leaf = we.attestations.find((a) => a.attestation_id === leafId);
    const parts = we.attestations.filter((a) => a.attestation_id !== leafId);
    const withHash = [];
    for (const a of parts) withHash.push({ att: a, hash: await W.contentHash(a) });
    setIssued(withHash);
    setSignMsg(null); setResult(null); setVerifiedChain(null);
    // pre-fill the form for the final assembly the logged-in supplier performs
    setForm({ name: 'Recovery-Capable ISR Drone', action: 'final_integration', country: 'CA',
              qty: 1, unit: 'units', mat: 0, hrs: 5, lab: 400 });
    // the leaf consumes ONLY its real direct parents (not every deep raw; those
    // are already consumed upstream, which would double-count and trip mass-balance)
    setSelectedParents((leaf.parents || []).map((p) => p.attestation_id));
    setBusy(false);
  }

  function toggleParent(id) {
    setSelectedParents((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  }

  async function signAttestation() {
    setBusy(true); setSignMsg(null);
    const day = new Date().toISOString().slice(0, 10);
    const tod = form.action === 'raw_material_supply' ? '09:00:00Z' : '14:30:00Z';
    // build parents from selected issued attestations (auto id + content_hash + unit)
    const parents = issued
      .filter((it) => selectedParents.includes(it.att.attestation_id))
      .map((it) => ({
        attestation_id: it.att.attestation_id,
        content_hash: it.hash,
        quantity_consumed: 1,
        unit: it.att.output?.unit || 'units',
      }));
    const att = {
      attestation_id: 'att-' + crypto.randomUUID(),
      version: '1.0',
      supplier_id: wallet.supplier_id,
      timestamp: `${day}T${tod}`,
      action_type: form.action,
      performed_in_country: form.country,
      parents,
      output: { name: form.name || 'Output', quantity_produced: num(form.qty), unit: form.unit || 'units' },
      costs: { material_cad: num(form.mat), labour_hours: num(form.hrs), labour_cost_cad: num(form.lab) },
    };
    try {
      const signed = await W.sign(att, wallet.priv);
      const hash = await W.contentHash(signed);
      setIssued([...issued, { att: signed, hash }]);
      setSignMsg({ id: att.attestation_id, hash, sig: signed.signature.value, leaf: att });
      setSelectedParents([]);
    } catch (e) { setSignMsg({ error: e.message }); }
    finally { setBusy(false); }
  }

  async function verifyMine(leafId) {
    if (!issued.length) return;
    setBusy(true); setResult(null); setPublished(null);
    const leaf = leafId || issued[issued.length - 1].att.attestation_id;
    const attestations = issued.map((it) => it.att);
    try {
      const r = await verifyChain({ product_attestation_id: leaf, attestations });
      setVerifiedChain({ product_attestation_id: leaf, attestations });
      setResult(r);
    } catch (e) { setSignMsg({ error: e.message }); }
    finally { setBusy(false); }
  }

  async function publishMine() {
    if (!verifiedChain) return;
    setBusy(true);
    try {
      const res = await publishProduct(verifiedChain);
      setPublished(res);
      refreshProducts();
    } catch (e) { setSignMsg({ error: e.message }); }
    finally { setBusy(false); }
  }

  function startNew() {
    setForm({ name: 'Carbon Fibre Frame', action: 'raw_material_supply', country: 'CA', qty: 1, unit: 'units', mat: 500, hrs: 0, lab: 0 });
    setIssued([]); setSelectedParents([]); setSignMsg(null); setResult(null); setVerifiedChain(null); setPublished(null);
    setTab('new');
  }

  const isTransform = form.action !== 'raw_material_supply';

  return (
    <div className="space-y-6">
      <div className="card flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-aegis-muted">Authenticated wallet</div>
          <div className="font-display font-bold text-2xl text-aegis-deep">{wallet.name}</div>
          <div className="mono text-sm text-aegis-muted">{wallet.supplier_id} · key verified ✓</div>
        </div>
        <button className="btn btn-outline" onClick={onLogout}>Sign out</button>
      </div>

      {/* tabs */}
      <div className="flex gap-2 border-b border-aegis-line">
        {[['dashboard', 'My products'], ['new', 'New submission']].map(([k, label]) => (
          <button key={k} data-testid={`tab-${k}`}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? 'border-aegis-blue text-aegis-blue' : 'border-transparent text-aegis-muted'}`}
            onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === 'dashboard' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-aegis-deep">Published products</h3>
            <button className="btn btn-primary" onClick={startNew} data-testid="new-submission">+ New submission</button>
          </div>
          {loadingProducts && <div className="card text-aegis-muted">Loading…</div>}
          {!loadingProducts && products.length === 0 && (
            <div className="card text-aegis-muted text-sm">
              No products published yet. Click <strong>New submission</strong> to sign a chain and publish it.
            </div>
          )}
          <div className="grid md:grid-cols-2 gap-4">
            {products.map((p) => (
              <div key={p.product_id} className="card flex items-center gap-4" data-testid="product-card">
                <img src={qrUrl(p.product_id)} alt="QR" className="w-24 h-24" />
                <div className="min-w-0">
                  <div className="font-display font-bold text-aegis-deep truncate">{p.name}</div>
                  <div className="mono text-xs text-aegis-muted truncate">{p.product_id}</div>
                  <a className="btn btn-outline mt-2 text-xs" href={`/purchaser?pid=${encodeURIComponent(p.product_id)}`} target="_blank" rel="noreferrer">
                    Open in Purchaser →
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'new' && <>
      <div className="card border-aegis-blue/30 bg-aegis-blue/5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="text-sm text-aegis-ink">
            <strong className="text-aegis-deep">Build a full product chain.</strong> Sign raw materials,
            then a final assembly that consumes them, or load the demo drone's upstream parts to skip ahead.
          </div>
          <button className="btn btn-outline whitespace-nowrap" onClick={seedDroneParts} disabled={busy} data-testid="seed-parts">
            Load demo drone parts
          </button>
        </div>
      </div>

      <div className="card space-y-4">
        <h3 className="font-bold text-aegis-deep">Issue a signed attestation</h3>
        <div className="grid md:grid-cols-2 gap-4">
          <div><label className="label">Output name</label><input className="input" value={form.name} onChange={set('name')} /></div>
          <div><label className="label">Action type</label>
            <select className="input" value={form.action} onChange={set('action')}>
              {ACTIONS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </div>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <div><label className="label">Performed in country</label>
            <select className="input" value={form.country} onChange={set('country')}>
              {COUNTRIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div><label className="label">Output quantity</label><input type="number" className="input" value={form.qty} onChange={set('qty')} /></div>
          <div><label className="label">Output unit</label><input className="input" value={form.unit} onChange={set('unit')} /></div>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <div><label className="label">Material cost (CAD)</label><input type="number" className="input" value={form.mat} onChange={set('mat')} /></div>
          <div><label className="label">Labour hours{isTransform && ' (≥4 = substantial)'}</label><input type="number" className="input" value={form.hrs} onChange={set('hrs')} /></div>
          <div><label className="label">Labour cost (CAD)</label><input type="number" className="input" value={form.lab} onChange={set('lab')} /></div>
        </div>

        {/* pick parents from issued attestations, no manual hashes */}
        {issued.length > 0 && (
          <div>
            <label className="label">Inputs consumed (pick from your issued attestations)</label>
            <div className="flex flex-wrap gap-2">
              {issued.map((it) => {
                const on = selectedParents.includes(it.att.attestation_id);
                return (
                  <button key={it.att.attestation_id} type="button"
                    onClick={() => toggleParent(it.att.attestation_id)}
                    className={`badge border ${on ? 'bg-aegis-blue text-white border-aegis-blue' : 'border-aegis-line text-aegis-muted'}`}>
                    {on ? '✓ ' : ''}{it.att.output?.name || it.att.attestation_id.slice(0, 10)}
                  </button>
                );
              })}
            </div>
            {isTransform && selectedParents.length === 0 && (
              <p className="text-xs text-aegis-amber mt-1">A {form.action} normally consumes at least one input.</p>
            )}
          </div>
        )}

        <button className="btn btn-primary" disabled={busy} onClick={signAttestation}>Sign attestation</button>
        {signMsg && !signMsg.error && (
          <div className="border-aegis-green/40 bg-aegis-green/5 border rounded-lg p-3 text-sm">
            <strong className="text-aegis-green">Attestation signed.</strong><br />
            ID: <span className="mono" data-testid="last-att-id">{signMsg.id}</span><br />
            content_hash: <span className="mono text-xs">{signMsg.hash}</span>
            <div className="mt-2">
              <button className="btn btn-success" onClick={() => verifyMine(signMsg.id)} data-testid="verify-this">
                Verify this product via /verify →
              </button>
            </div>
          </div>
        )}
        {signMsg?.error && <div className="text-aegis-red text-sm">{signMsg.error}</div>}
      </div>

      <div className="card space-y-3">
        <h3 className="font-bold text-aegis-deep">Attestations issued this session ({issued.length})</h3>
        {!issued.length && <p className="text-aegis-muted text-sm">None yet. Sign one above, or load the demo drone parts.</p>}
        {issued.length > 0 && (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-aegis-muted border-b border-aegis-line"><th className="py-1">Output</th><th>Action</th><th>Country</th><th>ID</th></tr></thead>
            <tbody>
              {issued.map((it, i) => (
                <tr key={i} className="border-b border-aegis-line/50">
                  <td className="py-1">{it.att.output.name}</td><td className="mono text-xs">{it.att.action_type}</td>
                  <td>{it.att.performed_in_country}</td><td className="mono text-xs">{it.att.attestation_id.slice(0, 14)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {result && <Verdict result={result} chain={verifiedChain} />}

        {result && result.chain_valid && !published && (
          <button className="btn btn-primary" disabled={busy} onClick={publishMine} data-testid="publish">
            Publish product & generate QR →
          </button>
        )}

        {published && (
          <div className="border border-aegis-green/40 bg-aegis-green/5 rounded-xl p-4 flex flex-col items-center gap-2" data-testid="qr-block">
            <div className="font-display font-bold text-aegis-deep">{published.name} published</div>
            <img src={qrUrl(published.product_id)} alt="Product QR" className="w-44 h-44" data-testid="qr-img" />
            <div className="mono text-xs text-aegis-muted">{published.product_id}</div>
            <div className="text-sm text-aegis-muted text-center">
              Print this on the product. Anyone can scan it in the Purchaser app to verify provenance.
            </div>
          </div>
        )}
      </div>
      </>}
    </div>
  );
}
