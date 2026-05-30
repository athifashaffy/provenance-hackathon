// Purchaser report export: JSON (audit record) + printable HTML (Save as PDF).

export function downloadJSON(result, chain, productName) {
  const report = {
    aegis_report_version: '1.0',
    generated_at: new Date().toISOString(),
    product_name: productName || '',
    product_attestation_id: chain?.product_attestation_id || result.product_attestation_id,
    verdict: {
      designation: result.designation,
      canadian_content_percentage: result.canadian_content_percentage,
      chain_valid: result.chain_valid,
      anomalies: result.anomalies || [],
    },
    chain: chain || null,
  };
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  triggerDownload(blob, `aegis-report-${shortId(report.product_attestation_id)}.json`);
}

export function printReport(result, chain, productName) {
  const dz = {
    product_of_canada: 'Product of Canada',
    made_in_canada: 'Made in Canada',
    none: 'Not Qualified',
  }[result.designation] || 'Not Qualified';
  const pct = Number(result.canadian_content_percentage).toFixed(1);
  const valid = result.chain_valid;
  const anoms = result.anomalies || [];
  const atts = chain?.attestations || [];
  const now = new Date().toLocaleString();
  const pid = chain?.product_attestation_id || result.product_attestation_id || '';

  const rows = atts.map((a) => `
    <tr>
      <td>${esc(a.output?.name || '-')}</td>
      <td class="mono">${esc(a.action_type || '')}</td>
      <td>${esc(a.performed_in_country || '?')}</td>
      <td class="r">${(a.costs?.material_cad || 0).toFixed(2)}</td>
      <td class="r">${(a.costs?.labour_cost_cad || 0).toFixed(2)}</td>
    </tr>`).join('');

  const anomHtml = anoms.length
    ? `<h3>Anomalies (${anoms.length})</h3>` + anoms.map((a) =>
        `<div class="anom"><b>${esc(a.type)}</b> <span class="mono">${esc((a.attestation_id || '').slice(0, 18))}</span><br><span class="muted">${esc(a.details || '')}</span></div>`).join('')
    : `<p class="ok">No integrity violations. Every signature verified, every hash link intact.</p>`;

  const html = `<!doctype html><html><head><meta charset="utf-8"><title>AEGIS Report ${esc(shortId(pid))}</title>
  <style>
    body{font-family:-apple-system,Segoe UI,Inter,sans-serif;color:#16213e;margin:40px;}
    .head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #2f4fb0;padding-bottom:10px;}
    .brand{font-weight:700;font-size:24px;color:#2f4fb0;letter-spacing:.04em;}
    .verdict{background:${valid ? '#1f3a8a' : '#d83434'};color:#fff;border-radius:12px;padding:18px 22px;margin:18px 0;}
    .verdict .dz{font-size:30px;font-weight:700;}
    .verdict .pct{font-size:18px;opacity:.9;}
    .badge{display:inline-block;background:rgba(255,255,255,.2);border-radius:20px;padding:3px 10px;font-size:12px;margin-right:6px;margin-top:8px;}
    table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px;}
    th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e0e6f2;}
    th{color:#5b6b8c;font-size:11px;text-transform:uppercase;letter-spacing:.05em;}
    .r{text-align:right;} .mono{font-family:ui-monospace,monospace;font-size:11px;}
    .muted{color:#5b6b8c;font-size:12px;} .ok{color:#1f6b4f;}
    .anom{border-left:3px solid #d83434;padding:4px 10px;margin:6px 0;}
    .meta{color:#5b6b8c;font-size:12px;margin-top:4px;}
    @media print{body{margin:16px;}}
  </style></head><body>
    <div class="head"><div class="brand">AEGIS</div><div class="meta">Verification report · ${esc(now)}</div></div>
    <h2>${esc(productName || 'Product')}</h2>
    <div class="meta mono">${esc(pid)}</div>
    <div class="verdict">
      <div class="dz">${esc(dz)}</div>
      <div class="pct">${pct}% Canadian content</div>
      <div><span class="badge">${valid ? 'CHAIN VERIFIED' : 'CHAIN INVALID'}</span>
      <span class="badge">${atts.length} attestations</span>
      <span class="badge">${anoms.length} integrity violation(s)</span></div>
    </div>
    ${anomHtml}
    <h3>Supply chain (${atts.length} tiers)</h3>
    <table><thead><tr><th>Output</th><th>Action</th><th>Country</th><th class="r">Material $</th><th class="r">Labour $</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="meta">Verified by AEGIS against the cryptographic provenance registry. Signatures checked end to end on the device that produced this report.</p>
    <script>window.onload=()=>window.print();</script>
  </body></html>`;

  const w = window.open('', '_blank');
  if (!w) { alert('Allow pop-ups to print the report.'); return; }
  w.document.write(html);
  w.document.close();
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
function shortId(id) { return (id || 'report').replace(/^att-/, '').slice(0, 8); }
function esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
