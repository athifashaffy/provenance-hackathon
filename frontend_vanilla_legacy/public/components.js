/**
 * TAN Supply Chain — UI Component Module
 *
 * All UI is built from pure functions that return HTML strings.
 * No framework dependency — drop into any page with a <script> tag.
 *
 * Architecture notes for future Figma MCP integration:
 *   Each component is isolated and receives only data (no DOM coupling).
 *   To apply a new design system, swap the template literals inside each
 *   function. The calling code (renderReport, renderSupplierChain, etc.)
 *   does not need to change — it passes the same data shape.
 *
 * Usage:
 *   <script src="components.js"></script>
 *   document.getElementById('wrap').innerHTML = Components.designationHero(data);
 */

const Components = (() => {
  'use strict';

  // ── Utility helpers ────────────────────────────────────────────────────────

  /** Escape user-controlled strings before injecting into innerHTML. */
  function esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** Truncate a hex ID for display: "abc123...def456" */
  function shortId(id, head = 10, tail = 6) {
    if (!id || id.length <= head + tail + 3) return esc(id);
    return `${esc(id.slice(0, head))}…${esc(id.slice(-tail))}`;
  }

  /** Format a CAD dollar amount with commas and two decimal places. */
  function fmtCAD(n) {
    return '$' + Number(n).toLocaleString('en-CA', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  /** Map designation string → CSS class suffix. */
  function designationClass(d) {
    const map = {
      'Product of Canada': 'product-of-canada',
      'Made in Canada':    'made-in-canada',
      'Not Qualified':     'not-qualified',
    };
    return map[d] || 'unknown';
  }

  /** Bar colour class based on Canadian content percentage. */
  function barClass(pct) {
    if (pct >= 98) return 'high';
    if (pct >= 51) return 'med';
    return 'low';
  }

  // ── Badge ──────────────────────────────────────────────────────────────────

  /**
   * Badge component.
   * @param {string} text  - Label text
   * @param {'success'|'warning'|'danger'|'info'} variant
   */
  function badge(text, variant = 'info') {
    return `<span class="badge badge-${esc(variant)}">${esc(text)}</span>`;
  }

  // ── Alert ──────────────────────────────────────────────────────────────────

  /**
   * Alert banner component.
   * @param {string} message
   * @param {'success'|'warning'|'danger'|'info'} variant
   */
  function alert(message, variant = 'info', raw = false) {
    return `<div class="alert alert-${esc(variant)}">${raw ? message : esc(message)}</div>`;
  }

  // ── Spinner ────────────────────────────────────────────────────────────────

  /** Inline loading spinner. */
  function spinner(label = 'Loading…') {
    return `<span class="spinner" aria-label="${esc(label)}"></span> ${esc(label)}`;
  }

  // ── Stat card ─────────────────────────────────────────────────────────────

  /**
   * Individual metric card (for use inside a .stat-grid).
   * @param {string} value  - Large display value (already formatted)
   * @param {string} label  - Small uppercase label below the value
   */
  function statCard(value, label) {
    return `
      <div class="stat-card">
        <div class="stat-value">${value}</div>
        <div class="stat-label">${esc(label)}</div>
      </div>`;
  }

  // ── Designation hero ──────────────────────────────────────────────────────

  /**
   * Full-width hero banner showing the Canadian content designation.
   *
   * @param {{
   *   designation: string,
   *   canadian_content_pct: number,
   *   last_transformation_in_canada: boolean
   * }} data
   */
  function designationHero(data) {
    const pct = Number(data.canadian_content_pct || 0);
    const cls = designationClass(data.designation);
    const lastXform = data.last_transformation_in_canada ? 'Yes' : 'No';

    return `
      <div class="designation-hero designation-${cls}">
        <div class="designation-pct">${pct.toFixed(1)}%</div>
        <div class="designation-label">Canadian Content</div>
        <div class="designation-title" style="margin-top:.75rem;">
          ${esc(data.designation)}
        </div>
        <div style="font-size:.8rem;opacity:.8;margin-top:.3rem;">
          Last transformation in Canada: ${lastXform}
        </div>
      </div>`;
  }

  // ── Stats grid ─────────────────────────────────────────────────────────────

  /**
   * Four-card metric grid for a provenance report.
   *
   * @param {{
   *   total_cost_cad: number,
   *   canadian_cost_cad: number,
   *   chain_length: number,
   *   anomalies: Array
   * }} data
   */
  function statsGrid(data) {
    const hasAnomalies = data.anomalies && data.anomalies.length > 0;
    const anomalyBadge = hasAnomalies
      ? badge(`${data.anomalies.length} Issues`, 'danger')
      : badge('Clean', 'success');

    return `
      <div class="stat-grid">
        ${statCard(fmtCAD(data.total_cost_cad), 'Total Cost (CAD)')}
        ${statCard(fmtCAD(data.canadian_cost_cad), 'Canadian Cost (CAD)')}
        ${statCard(String(data.chain_length), 'Chain Depth')}
        ${statCard(anomalyBadge, 'Anomalies')}
      </div>`;
  }

  // ── Canadian content progress bar + breakdown table ───────────────────────

  /**
   * Progress bar + cost breakdown table card.
   *
   * @param {{
   *   canadian_cost_cad: number,
   *   canadian_content_pct: number,
   *   cost_breakdown: Array<{name,type,country,cost_cad,is_canadian}>
   * }} data
   */
  function contentBreakdown(data) {
    const pct = Number(data.canadian_content_pct || 0);
    const cls = barClass(pct);

    const rows = (data.cost_breakdown || []).map(row => `
      <tr>
        <td>${esc(row.name)}</td>
        <td>${badge(row.type, 'info')}</td>
        <td>${esc(row.country)}</td>
        <td>${fmtCAD(row.cost_cad)}</td>
        <td>${badge(row.is_canadian ? 'Yes' : 'No', row.is_canadian ? 'success' : 'danger')}</td>
      </tr>`).join('');

    return `
      <div class="card">
        <div class="card-title">Canadian Content Breakdown</div>
        <div style="display:flex;justify-content:space-between;font-size:.85rem;margin-bottom:.4rem;">
          <span>${fmtCAD(data.canadian_cost_cad)} Canadian</span>
          <span>${pct.toFixed(1)}%</span>
        </div>
        <div class="progress-wrap">
          <div class="progress-bar ${cls}" style="width:${Math.min(pct, 100)}%"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:.4rem;font-size:.75rem;color:var(--tan-gray);">
          <span>0%</span>
          <span style="color:var(--tan-warning);">51% Made in Canada</span>
          <span style="color:var(--tan-blue);">98% Product of Canada</span>
          <span>100%</span>
        </div>
        <div class="table-scroll" style="margin-top:1.25rem;">
          <table>
            <thead>
              <tr>
                <th>Component</th><th>Type</th><th>Country</th>
                <th>Cost (CAD)</th><th>Canadian?</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // ── Anomaly list ──────────────────────────────────────────────────────────

  /**
   * Anomaly cards or "clean" confirmation.
   *
   * @param {Array<{type:string, detail:string, attestation_id?:string}>} anomalies
   */
  function anomalyList(anomalies) {
    if (!anomalies || anomalies.length === 0) {
      return `
        <div class="card">
          ${alert('No anomalies detected — chain integrity verified.', 'success')}
        </div>`;
    }

    const items = anomalies.map(a => `
      <div class="anomaly-item">
        <div>
          <div class="anomaly-type">${esc(a.type || 'anomaly')}</div>
          <div style="margin-top:.2rem;">${esc(a.detail || '')}</div>
          ${a.attestation_id
            ? `<div class="mono" style="margin-top:.3rem;">${shortId(a.attestation_id)}</div>`
            : ''}
        </div>
      </div>`).join('');

    return `
      <div class="card">
        <div class="card-title" style="color:var(--tan-danger);">
          Anomalies Detected
        </div>
        ${items}
      </div>`;
  }

  // ── Supply chain DAG visualisation ────────────────────────────────────────

  /**
   * Vertical chain-of-custody diagram (list view).
   */
  function supplyChainList(nodes) {
    if (!nodes || nodes.length === 0) {
      return `<div class="card">${alert('No chain data available.', 'warning')}</div>`;
    }

    const nodeHTML = nodes.map((node, i) => {
      const dotClass = i === 0 ? 'root' : node.sig_valid === false ? 'invalid' : '';
      const loc = node.location || {};
      const locationStr = [loc.country, loc.province].filter(Boolean).join(', ');
      const inputList = (node.inputs || []).length
        ? `<div style="font-size:.75rem;color:var(--tan-gray);margin-top:.3rem;">
             Inputs: ${(node.inputs || []).map(id => shortId(id)).join(', ')}
           </div>`
        : '';

      return `
        <div class="chain-node">
          <div class="chain-dot ${dotClass}">${i + 1}</div>
          <div class="chain-content">
            <div class="chain-name">${esc(node.product_name)}</div>
            <div class="chain-meta">
              Supplier: <strong>${esc(node.supplier_id)}</strong>
              ${locationStr ? `&bull; ${esc(locationStr)}` : ''}
              &bull;
              ${badge(node.sig_valid ? 'Sig OK' : 'Sig FAIL', node.sig_valid ? 'success' : 'danger')}
            </div>
            <div class="mono" style="margin-top:.3rem;">${shortId(node.attestation_id)}</div>
            ${inputList}
          </div>
        </div>`;
    }).join('');

    return nodeHTML;
  }

  /**
   * Interactive DAG graph visualization using SVG.
   * Builds a layered tree from the supplier_chain data, renders nodes
   * as rounded rectangles connected by curved edges.
   */
  function dagGraph(nodes) {
    if (!nodes || nodes.length === 0) return '';

    // Build adjacency: parent -> children (parent references children as inputs)
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.attestation_id] = n; });

    // Assign depth levels using BFS from root (index 0)
    const root = nodes[0];
    const levels = {};
    const queue = [[root.attestation_id, 0]];
    const visited = new Set();

    while (queue.length > 0) {
      const [id, depth] = queue.shift();
      if (visited.has(id)) continue;
      visited.add(id);
      levels[id] = depth;
      const node = nodeMap[id];
      if (node && node.inputs) {
        node.inputs.forEach(inputId => {
          if (nodeMap[inputId] && !visited.has(inputId)) {
            queue.push([inputId, depth + 1]);
          }
        });
      }
    }

    // Group nodes by level
    const maxDepth = Math.max(...Object.values(levels), 0);
    const levelGroups = {};
    for (let i = 0; i <= maxDepth; i++) levelGroups[i] = [];
    Object.entries(levels).forEach(([id, d]) => {
      levelGroups[d].push(id);
    });

    // Layout constants
    const nodeW = 220, nodeH = 80, gapX = 40, gapY = 100;
    const paddingX = 30, paddingY = 30;

    // Compute positions
    const positions = {};
    let maxWidth = 0;
    for (let d = 0; d <= maxDepth; d++) {
      const group = levelGroups[d];
      const totalW = group.length * nodeW + (group.length - 1) * gapX;
      if (totalW > maxWidth) maxWidth = totalW;
    }

    for (let d = 0; d <= maxDepth; d++) {
      const group = levelGroups[d];
      const totalW = group.length * nodeW + (group.length - 1) * gapX;
      const startX = paddingX + (maxWidth - totalW) / 2;
      group.forEach((id, i) => {
        positions[id] = {
          x: startX + i * (nodeW + gapX),
          y: paddingY + d * (nodeH + gapY),
        };
      });
    }

    const svgW = maxWidth + paddingX * 2;
    const svgH = (maxDepth + 1) * (nodeH + gapY) - gapY + paddingY * 2;

    // Draw edges
    let edges = '';
    nodes.forEach(node => {
      if (!node.inputs || !positions[node.attestation_id]) return;
      const from = positions[node.attestation_id];
      const fromCx = from.x + nodeW / 2;
      const fromCy = from.y + nodeH;

      node.inputs.forEach(inputId => {
        if (!positions[inputId]) return;
        const to = positions[inputId];
        const toCx = to.x + nodeW / 2;
        const toCy = to.y;
        const midY = (fromCy + toCy) / 2;
        edges += `<path d="M${fromCx},${fromCy} C${fromCx},${midY} ${toCx},${midY} ${toCx},${toCy}"
                   stroke="var(--tan-border)" stroke-width="2" fill="none"
                   marker-end="url(#arrowhead)"/>`;
      });
    });

    // Draw nodes
    let nodesSvg = '';
    Object.entries(positions).forEach(([id, pos]) => {
      const node = nodeMap[id];
      if (!node) return;
      const loc = node.location || {};
      const isCA = loc.country === 'CA';
      const isRoot = id === root.attestation_id;
      const sigFail = node.sig_valid === false;

      let fill = 'var(--tan-sky)';
      let stroke = 'var(--tan-border)';
      let textColor = 'var(--tan-navy)';

      if (isRoot) { fill = 'var(--tan-navy)'; stroke = 'var(--tan-navy)'; textColor = 'white'; }
      else if (sigFail) { fill = 'var(--tan-danger-bg)'; stroke = 'var(--tan-danger)'; }
      else if (isCA) { fill = '#e0f2fe'; stroke = 'var(--tan-blue)'; }

      const flagEmoji = isCA ? '\u{1F1E8}\u{1F1E6}' : loc.country === 'US' ? '\u{1F1FA}\u{1F1F8}' : '\u{1F310}';
      const name = (node.product_name || '').length > 22
        ? node.product_name.slice(0, 20) + '...'
        : node.product_name || '';
      const supplier = (node.supplier_id || '').length > 20
        ? node.supplier_id.slice(0, 18) + '...'
        : node.supplier_id || '';

      nodesSvg += `
        <g class="dag-node" data-id="${esc(id)}">
          <rect x="${pos.x}" y="${pos.y}" width="${nodeW}" height="${nodeH}"
                rx="10" ry="10" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
          <text x="${pos.x + 12}" y="${pos.y + 24}" fill="${textColor}"
                font-size="13" font-weight="700">${flagEmoji} ${esc(name)}</text>
          <text x="${pos.x + 12}" y="${pos.y + 44}" fill="${isRoot ? 'rgba(255,255,255,.8)' : 'var(--tan-gray)'}"
                font-size="11">${esc(supplier)}</text>
          <text x="${pos.x + 12}" y="${pos.y + 62}" fill="${isRoot ? 'rgba(255,255,255,.6)' : 'var(--tan-gray)'}"
                font-size="10" font-family="monospace">${shortId(id, 8, 4)}</text>
          ${sigFail ? `<circle cx="${pos.x + nodeW - 16}" cy="${pos.y + 16}" r="8" fill="var(--tan-danger)"/>
            <text x="${pos.x + nodeW - 16}" y="${pos.y + 20}" fill="white" font-size="10" text-anchor="middle" font-weight="700">!</text>` : ''}
          ${!sigFail && !isRoot ? `<circle cx="${pos.x + nodeW - 16}" cy="${pos.y + 16}" r="8" fill="var(--tan-success)"/>
            <text x="${pos.x + nodeW - 16}" y="${pos.y + 20}" fill="white" font-size="9" text-anchor="middle">&#10003;</text>` : ''}
        </g>`;
    });

    return `
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="var(--tan-border)" />
        </marker>
      </defs>
      ${edges}
      ${nodesSvg}`;
  }

  /**
   * Full supply chain card with toggle between list and graph views.
   */
  function supplyChain(nodes) {
    if (!nodes || nodes.length === 0) {
      return `<div class="card">${alert('No chain data available.', 'warning')}</div>`;
    }

    // Build adjacency for dagGraph
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.attestation_id] = n; });
    const root = nodes[0];
    const levels = {};
    const queue = [[root.attestation_id, 0]];
    const vis = new Set();
    while (queue.length > 0) {
      const [id, depth] = queue.shift();
      if (vis.has(id)) continue;
      vis.add(id);
      levels[id] = depth;
      const node = nodeMap[id];
      if (node && node.inputs) {
        node.inputs.forEach(inputId => {
          if (nodeMap[inputId] && !vis.has(inputId)) queue.push([inputId, depth + 1]);
        });
      }
    }
    const maxDepth = Math.max(...Object.values(levels), 0);
    const nodeW = 220, nodeH = 80, gapX = 40, gapY = 100, paddingX = 30, paddingY = 30;
    const levelGroups = {};
    for (let i = 0; i <= maxDepth; i++) levelGroups[i] = [];
    Object.entries(levels).forEach(([id, d]) => { levelGroups[d].push(id); });
    let maxWidth = 0;
    for (let d = 0; d <= maxDepth; d++) {
      const w = levelGroups[d].length * nodeW + (levelGroups[d].length - 1) * gapX;
      if (w > maxWidth) maxWidth = w;
    }
    const svgW = maxWidth + paddingX * 2;
    const svgH = (maxDepth + 1) * (nodeH + gapY) - gapY + paddingY * 2;

    const listHTML = supplyChainList(nodes);
    const graphSVG = dagGraph(nodes);

    return `
      <div class="card">
        <div class="card-title">
          Supply Chain DAG
          <div style="margin-left:auto;display:flex;gap:.5rem;">
            <button class="btn btn-outline dag-view-btn active" onclick="switchChainView('graph', this)" style="padding:.3rem .7rem;font-size:.75rem;">Graph</button>
            <button class="btn btn-outline dag-view-btn" onclick="switchChainView('list', this)" style="padding:.3rem .7rem;font-size:.75rem;">List</button>
          </div>
        </div>
        <div id="chain-view-graph" class="dag-graph-wrap" style="overflow-x:auto;">
          <svg width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}"
               style="min-width:${svgW}px;display:block;margin:0 auto;">
            ${graphSVG}
          </svg>
          <div style="text-align:center;margin-top:.75rem;">
            <div style="display:inline-flex;gap:1.25rem;font-size:.75rem;color:var(--tan-gray);">
              <span><span style="display:inline-block;width:12px;height:12px;background:var(--tan-navy);border-radius:3px;vertical-align:middle;margin-right:4px;"></span>Final Product</span>
              <span><span style="display:inline-block;width:12px;height:12px;background:#e0f2fe;border:2px solid var(--tan-blue);border-radius:3px;vertical-align:middle;margin-right:4px;"></span>Canadian</span>
              <span><span style="display:inline-block;width:12px;height:12px;background:var(--tan-sky);border:2px solid var(--tan-border);border-radius:3px;vertical-align:middle;margin-right:4px;"></span>International</span>
              <span><span style="display:inline-block;width:12px;height:12px;background:var(--tan-danger-bg);border:2px solid var(--tan-danger);border-radius:3px;vertical-align:middle;margin-right:4px;"></span>Sig Failure</span>
            </div>
          </div>
        </div>
        <div id="chain-view-list" style="display:none;">
          ${listHTML}
        </div>
      </div>`;
  }

  // ── QR code display ───────────────────────────────────────────────────────

  /**
   * QR code image card.
   * @param {string} apiBase   - e.g. "http://localhost:8000"
   * @param {string} attId     - attestation ID
   */
  function qrCard(apiBase, attId) {
    const src = `${apiBase}/api/qr/${encodeURIComponent(attId)}`;
    return `
      <div class="card">
        <div class="card-title">Share via QR Code</div>
        <div class="qr-wrap">
          <img src="${esc(src)}" alt="QR Code" width="200" height="200" />
        </div>
        <div style="text-align:center;margin-top:.5rem;">
          <div class="mono">${esc(attId)}</div>
        </div>
      </div>`;
  }

  // ── Full provenance report ────────────────────────────────────────────────

  /**
   * Compose a complete provenance report from API response data.
   * Replaces the inline renderReport() function in purchaser.html.
   *
   * @param {object} data  - Response from GET /api/product/:id
   * @param {string} apiBase
   */
  function provenanceReport(data, apiBase) {
    return [
      designationHero(data),
      statsGrid(data),
      contentBreakdown(data),
      anomalyList(data.anomalies),
      supplyChain(data.supplier_chain),
      qrCard(apiBase, data.product_attestation_id),
    ].join('\n');
  }

  // ── Dashboard supplier row ────────────────────────────────────────────────

  /**
   * A single <tr> for the dashboard supplier table.
   * @param {{supplier_id, name, country, province, created_at}} supplier
   */
  function supplierRow(supplier) {
    const loc = [supplier.country, supplier.province].filter(Boolean).join(', ');
    const date = supplier.created_at
      ? new Date(supplier.created_at).toLocaleDateString('en-CA')
      : '—';
    return `
      <tr>
        <td><span class="mono">${esc(supplier.supplier_id)}</span></td>
        <td>${esc(supplier.name)}</td>
        <td>${esc(loc)}</td>
        <td>${date}</td>
      </tr>`;
  }

  // ── Dashboard attestation row ─────────────────────────────────────────────

  /**
   * A single <tr> for the dashboard attestation table.
   * @param {{id, product_name, signer_id, sig_valid, created_at}} att
   * @param {string} purchaserBase  - base URL for the purchaser page
   */
  function attestationRow(att, purchaserBase = '') {
    const date = att.created_at
      ? new Date(att.created_at).toLocaleDateString('en-CA')
      : '—';
    const link = purchaserBase
      ? `<a href="${esc(purchaserBase)}/purchaser.html?id=${esc(att.id)}"
            style="color:var(--tan-blue);">${esc(att.product_name || '—')}</a>`
      : esc(att.product_name || '—');

    return `
      <tr>
        <td>${link}</td>
        <td><span class="mono">${shortId(att.id)}</span></td>
        <td>${esc(att.signer_id)}</td>
        <td>${badge(att.sig_valid ? 'Valid' : 'Invalid', att.sig_valid ? 'success' : 'danger')}</td>
        <td>${date}</td>
      </tr>`;
  }

  // ── Wallet connect card (supplier login) ─────────────────────────────────

  /**
   * Crypto-wallet-style login card for suppliers.
   * Once connected, shows identity badge + disconnect button.
   */
  function walletCard() {
    const stored = typeof sessionStorage !== 'undefined'
      ? sessionStorage.getItem('tan_wallet') : null;

    if (stored) {
      try {
        const wallet = JSON.parse(stored);
        return `
          <div class="card wallet-card wallet-connected">
            <div style="display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
              <div class="wallet-indicator connected"></div>
              <div style="flex:1;">
                <div style="font-weight:700;color:var(--tan-navy);font-size:.95rem;">Wallet Connected</div>
                <div style="font-size:.8rem;color:var(--tan-gray);">
                  <strong>${esc(wallet.supplier_id)}</strong> &bull; Key loaded in session
                </div>
              </div>
              <button class="btn btn-outline" onclick="disconnectWallet()" style="padding:.35rem .8rem;font-size:.8rem;">
                Disconnect
              </button>
            </div>
          </div>`;
      } catch (_) { /* fall through to login */ }
    }

    return `
      <div class="card wallet-card wallet-login">
        <div class="wallet-login-head">
          <div class="wallet-login-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <div>
            <div class="wallet-login-title">Connect Supplier Wallet</div>
            <div class="wallet-login-sub">Sign in to issue cryptographically signed attestations</div>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Supplier ID</label>
            <input id="wallet-id" placeholder="sup-acme-001" />
          </div>
          <div class="form-group">
            <label>Private Key (64-char hex)</label>
            <input id="wallet-key" type="password" placeholder="Your Ed25519 private key" autocomplete="off" />
          </div>
        </div>
        <p class="wallet-login-note">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          Your private key stays in browser memory only — it is never sent to the server.
        </p>
        <button class="btn btn-primary btn-block" onclick="connectWallet()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Connect Wallet
        </button>
        <div class="wallet-login-alt">
          New supplier?
          <a onclick="document.getElementById('register-section').style.display='block';">Register an identity</a>
        </div>
        <div id="wallet-result" style="margin-top:.75rem;"></div>
      </div>`;
  }

  // ── Public API ────────────────────────────────────────────────────────────

  return {
    // Primitives
    badge,
    alert,
    spinner,
    statCard,
    // Composite
    designationHero,
    statsGrid,
    contentBreakdown,
    anomalyList,
    supplyChain,
    supplyChainList,
    dagGraph,
    qrCard,
    provenanceReport,
    walletCard,
    // Table rows
    supplierRow,
    attestationRow,
    // Utilities (exposed for testing)
    _esc: esc,
    _shortId: shortId,
    _fmtCAD: fmtCAD,
  };
})();
