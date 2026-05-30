import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import jsQR from 'jsqr';
import demo from '../demo-data.json';
import { verifyChain, resolveProduct } from '../lib/api.js';
import { downloadJSON, printReport } from '../lib/report.js';
import Verdict from '../components/Verdict.jsx';

export default function Purchaser() {
  const [params, setParams] = useSearchParams();
  const [result, setResult] = useState(null);
  const [chain, setChain] = useState(null);
  const [productName, setProductName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pid, setPid] = useState('');
  const [scanning, setScanning] = useState(false);

  // auto-resolve when arriving from a scanned QR deep-link (?pid=...)
  useEffect(() => {
    const q = params.get('pid');
    if (q) { setPid(q); lookup(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runVerify(c, name) {
    setLoading(true); setError(''); setResult(null);
    try {
      const r = await verifyChain(c);
      setChain(c); setProductName(name || ''); setResult(r);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function lookup(id) {
    const productId = (id || pid).trim();
    if (!productId) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const data = await resolveProduct(productId);
      await runVerify(data.chain, data.name);
      setParams({ pid: productId }, { replace: true });
    } catch (e) { setError(e.message); setLoading(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-3xl text-aegis-blue">Verify Product Provenance</h1>
        <p className="text-aegis-muted mt-1">
          Scan a product's QR code (or enter its ID) to resolve its full supply chain and verify
          its Canadian-content designation, independently, in one call.
        </p>
      </div>

      <div className="card space-y-4">
        <h3 className="font-bold text-aegis-deep">Look up a product</h3>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[240px]">
            <label className="label">Product ID</label>
            <input className="input mono text-sm" value={pid} onChange={(e) => setPid(e.target.value)}
              placeholder="att-… (from the QR code)" onKeyDown={(e) => e.key === 'Enter' && lookup()} />
          </div>
          <button className="btn btn-primary" onClick={() => lookup()}>Verify</button>
          <button className="btn btn-outline" data-testid="scan-toggle" onClick={() => setScanning((s) => !s)}>
            {scanning ? 'Stop scan' : '📷 Scan QR'}
          </button>
        </div>

        {scanning && <Scanner onResult={(text) => { setScanning(false); const id = parsePid(text); setPid(id); lookup(id); }} />}

        <div className="border-t border-aegis-line pt-3">
          <div className="label">Demo products (verify a sample chain directly)</div>
          <div className="flex flex-wrap gap-2 mt-2">
            {demo.samples.map((s) => (
              <button key={s.id} data-testid={`sample-${s.id}`}
                className={`btn ${s.id === 'clean' ? 'btn-success' : 'btn-outline'}`}
                onClick={() => runVerify(s.chain, s.label)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* what AEGIS checks: the verification categories */}
      {!result && !loading && (
        <div className="card">
          <div className="label">Every chain is checked across four categories</div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-2">
            {[
              ['🔐', 'Integrity & identity', 'Every signature verifies against the registered supplier key; nothing was altered after signing.'],
              ['🔗', 'Chain structure', 'Hash-linked parents, no missing references, no cycles, no impossible timestamps.'],
              ['⚖️', 'Mass balance', 'No node consumes more material than its upstream suppliers ever produced.'],
              ['📊', 'Statistical anomalies', 'Cost, labour, timing and origin patterns checked against genuine supply chains.'],
            ].map(([icon, title, desc]) => (
              <div key={title} className="rounded-xl border border-aegis-line p-3">
                <div className="text-xl">{icon}</div>
                <div className="font-display font-bold text-sm text-aegis-deep mt-1">{title}</div>
                <div className="text-xs text-aegis-muted mt-1 leading-snug">{desc}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && <div className="card text-aegis-muted">Resolving & verifying…</div>}
      {error && <div className="card border-aegis-red/40 bg-aegis-red/5 text-aegis-red text-sm">{error}</div>}
      {result && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3">
            {productName ? <div className="font-display font-bold text-xl text-aegis-deep">{productName}</div> : <div />}
            <div className="flex gap-2">
              <button className="btn btn-primary" data-testid="save-pdf" onClick={() => printReport(result, chain, productName)}>
                Save report (PDF)
              </button>
              <button className="btn btn-outline" data-testid="save-json" onClick={() => downloadJSON(result, chain, productName)}>
                Download JSON
              </button>
              {pid && (
                <button className="btn btn-outline" onClick={() => {
                  navigator.clipboard?.writeText(`${window.location.origin}${import.meta.env.BASE_URL}purchaser?pid=${pid}`);
                }}>
                  Copy link
                </button>
              )}
            </div>
          </div>
          <Verdict result={result} chain={chain} />
        </>
      )}
    </div>
  );
}

function parsePid(text) {
  try { return new URL(text).searchParams.get('pid') || text; }
  catch { return text; }
}

function Scanner({ onResult }) {
  const videoRef = useRef(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let stream, raf, cancelled = false;
    const canvas = document.createElement('canvas');
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        if (cancelled) return;
        const v = videoRef.current;
        v.srcObject = stream; await v.play();
        const tick = () => {
          if (cancelled) return;
          if (v.readyState === v.HAVE_ENOUGH_DATA) {
            canvas.width = v.videoWidth; canvas.height = v.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const code = jsQR(img.data, img.width, img.height);
            if (code) { onResult(code.data); return; }
          }
          raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      } catch (e) { setErr('Camera unavailable: ' + e.message); }
    })();
    return () => { cancelled = true; if (raf) cancelAnimationFrame(raf); if (stream) stream.getTracks().forEach((t) => t.stop()); };
  }, [onResult]);

  return (
    <div className="flex flex-col items-center">
      <video ref={videoRef} className="w-full max-w-sm rounded-xl border-2 border-aegis-blue" playsInline muted />
      {err ? <div className="text-aegis-red text-sm mt-2">{err}</div>
           : <div className="text-aegis-muted text-sm mt-2">Point the camera at a product QR code…</div>}
    </div>
  );
}
