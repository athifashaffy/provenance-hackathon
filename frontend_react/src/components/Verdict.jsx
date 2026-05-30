import ChainGraph from './ChainGraph.jsx';
import { categorize } from '../lib/categories.js';

const STATUS = {
  pass: { label: 'PASS', badge: 'bg-aegis-green/15 text-aegis-green', bar: 'border-aegis-green', dot: '✓' },
  fail: { label: 'FAIL', badge: 'bg-aegis-red/15 text-aegis-red', bar: 'border-aegis-red', dot: '✗' },
  flag: { label: 'REVIEW', badge: 'bg-aegis-amber/15 text-aegis-amber', bar: 'border-aegis-amber', dot: '!' },
};

const DZ = {
  product_of_canada: { title: 'Product of Canada', cls: 'bg-aegis-green' },
  made_in_canada: { title: 'Made in Canada', cls: 'bg-aegis-blue' },
  none: { title: 'Not Qualified', cls: 'bg-aegis-amber' },
};

export default function Verdict({ result, chain }) {
  if (!result) return null;
  const dz = DZ[result.designation] || DZ.none;
  const all = result.anomalies || [];
  const hard = all.filter((a) => a.type !== 'statistical_outlier');
  const atts = (chain && chain.attestations) || [];
  const valid = result.chain_valid;
  const pct = Number(result.canadian_content_percentage);

  // explain a "none" verdict so it never looks contradictory next to a high %
  let why = '';
  if (result.designation === 'none') {
    const TR = new Set(['component_manufacture', 'subassembly', 'final_integration']);
    const hasSubstantial = atts.some((a) => TR.has(a.action_type) && (a.costs?.labour_hours || 0) >= 4);
    if (pct < 51) why = `Below the 51% Canadian-content threshold.`;
    else if (!hasSubstantial) why = `No substantial transformation in the chain (needs a manufacturing step with ≥4 labour hours), so it can't carry a "Made in / Product of Canada" claim regardless of cost.`;
    else why = `The last substantial transformation was not performed in Canada.`;
  }

  return (
    <div className="space-y-4" data-testid="report">
      <div className={`card text-white ${dz.cls}`}>
        <div className="text-xs uppercase tracking-widest opacity-80">AEGIS verdict</div>
        <div className="font-display font-bold text-4xl mt-1" data-testid="designation">{dz.title}</div>
        <div className="text-2xl font-display font-semibold mt-1" data-testid="pct">
          {pct.toFixed(1)}% Canadian content
        </div>
        {why && <div className="text-sm mt-2 opacity-90" data-testid="why">{why}</div>}
        <div className="flex flex-wrap gap-2 mt-3">
          <span className={`badge ${valid ? 'bg-white/20' : 'bg-aegis-red'}`} data-testid="chain-valid">
            {valid ? 'CHAIN VERIFIED ✓' : 'CHAIN INVALID ✗'}
          </span>
          <span className="badge bg-white/20">{atts.length} attestations</span>
          <span className="badge bg-white/20">{hard.length} integrity violation(s)</span>
        </div>
      </div>

      {/* four verification categories, each PASS / FAIL / REVIEW */}
      <div className="card" data-testid="categories">
        <h3 className="font-bold text-aegis-deep mb-3">Verification breakdown</h3>
        <div className="grid sm:grid-cols-2 gap-3">
          {categorize(all).map((c) => {
            const st = STATUS[c.status];
            return (
              <div key={c.key} className={`rounded-xl border-l-4 ${st.bar} border border-aegis-line p-3`} data-testid={`cat-${c.key}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{c.icon}</span>
                    <span className="font-display font-bold text-sm text-aegis-deep">{c.title}</span>
                  </div>
                  <span className={`badge ${st.badge}`} data-testid={`cat-${c.key}-status`}>{st.dot} {st.label}</span>
                </div>
                {c.findings.length === 0 ? (
                  <div className="text-xs text-aegis-muted mt-1.5 leading-snug">{c.desc}</div>
                ) : (
                  <div className="mt-2 space-y-1.5">
                    {c.findings.map((a, i) => (
                      <div key={i} className="text-xs">
                        <span className="mono font-semibold text-aegis-ink">{a.type}</span>
                        <span className="mono text-aegis-muted"> · {(a.attestation_id || '').slice(0, 14)}…</span>
                        <div className="text-aegis-muted">{a.details}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {atts.length > 0 && <ChainGraph atts={atts} leafId={chain?.product_attestation_id} />}

      {atts.length > 0 && (
        <div className="card">
          <h3 className="font-bold text-aegis-deep mb-3">Supply chain ({atts.length} tiers)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-aegis-muted border-b border-aegis-line">
                  <th className="py-2">Output</th><th>Action</th><th>Country</th>
                  <th className="text-right">Material $</th><th className="text-right">Labour $</th>
                </tr>
              </thead>
              <tbody>
                {atts.map((a, i) => (
                  <tr key={i} className="border-b border-aegis-line/50">
                    <td className="py-2">{a.output?.name || '-'}</td>
                    <td className="mono text-xs">{a.action_type}</td>
                    <td>
                      <span className={`badge ${a.performed_in_country === 'CA' ? 'bg-aegis-green/15 text-aegis-green' : 'bg-aegis-blue/10 text-aegis-blue'}`}>
                        {a.performed_in_country}
                      </span>
                    </td>
                    <td className="text-right">{(a.costs?.material_cad || 0).toFixed(2)}</td>
                    <td className="text-right">{(a.costs?.labour_cost_cad || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
