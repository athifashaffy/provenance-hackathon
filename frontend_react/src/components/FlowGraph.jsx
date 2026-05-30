// Interactive provenance DAG (ReactFlow). Attestations are laid out by tier —
// raw materials on the left flowing right into the finished product. Nodes are
// colour-coded (Canada / foreign / leaf / flagged) and the consume-edges carry
// quantity labels. Anomalies from /verify highlight the offending node + edge.

import { useMemo } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap, Handle, Position, MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';

const ACTION_LABEL = {
  raw_material_supply: 'Raw material',
  component_manufacture: 'Component',
  subassembly: 'Subassembly',
  final_integration: 'Final integration',
};

const COL_W = 280;   // horizontal spacing between tiers
const ROW_H = 132;   // vertical spacing within a tier

// depth = longest path from the leaf, so raw materials sit at the deepest tier
function computeDepths(atts, leafId) {
  const byId = Object.fromEntries(atts.map((a) => [a.attestation_id, a]));
  const depth = {};
  const walk = (id, d, seen) => {
    if (!byId[id] || seen.has(id)) return;
    seen.add(id);
    depth[id] = Math.max(depth[id] ?? 0, d);
    for (const p of byId[id].parents || []) walk(p.attestation_id, d + 1, seen);
    seen.delete(id);
  };
  walk(leafId, 0, new Set());
  const maxD = Math.max(0, ...Object.values(depth));
  atts.forEach((a) => { if (depth[a.attestation_id] == null) depth[a.attestation_id] = maxD; });
  return { depth, maxD };
}

// ── Custom node ────────────────────────────────────────────────────────────────
function AttNode({ data }) {
  const { att, isLeaf, flags } = data;
  const ca = att.performed_in_country === 'CA';
  const flagged = flags && flags.length > 0;
  const cost = (att.costs?.material_cad || 0) + (att.costs?.labour_cost_cad || 0);

  const ring = flagged ? 'border-aegis-red shadow-[0_0_0_3px_rgba(216,52,52,0.18)]'
    : isLeaf ? 'border-aegis-deep'
    : ca ? 'border-aegis-green' : 'border-aegis-line';
  const head = isLeaf ? 'bg-gradient-to-r from-aegis-blue to-aegis-deep text-white'
    : flagged ? 'bg-aegis-red/10 text-aegis-red' : 'bg-aegis-bg text-aegis-deep';

  return (
    <div className={`rounded-xl border-2 bg-white w-[220px] overflow-hidden ${ring}`} style={{ boxShadow: '0 4px 14px rgba(22,33,62,0.08)' }}>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div className={`px-3 py-1.5 flex items-center justify-between ${head}`}>
        <span className="font-display font-bold text-[0.72rem] uppercase tracking-wide">
          {ACTION_LABEL[att.action_type] || att.action_type}
        </span>
        <span className="text-[0.72rem] font-bold">
          {ca ? '🍁 CA' : att.performed_in_country}
        </span>
      </div>
      <div className="px-3 py-2">
        <div className="font-display font-bold text-sm text-aegis-ink leading-tight">
          {att.output?.name || att.attestation_id.slice(0, 12)}
        </div>
        <div className="text-[0.7rem] text-aegis-muted mono mt-0.5">{att.supplier_id}</div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-[0.72rem] text-aegis-muted">
            CA${cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            {att.costs?.labour_hours > 0 && ` · ${att.costs.labour_hours}h`}
          </span>
          <span className={`text-[0.7rem] font-bold ${flagged ? 'text-aegis-red' : 'text-aegis-green'}`}>
            {flagged ? '⚠ flagged' : '✓ valid'}
          </span>
        </div>
        {flagged && (
          <div className="mt-1.5 text-[0.66rem] text-aegis-red leading-snug mono">
            {flags.join(', ')}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { att: AttNode };

export default function FlowGraph({ atts, leafId, anomalies = [] }) {
  const { nodes, edges } = useMemo(() => {
    if (!atts?.length) return { nodes: [], edges: [] };

    // attestation_id -> [anomaly type] (skip soft statistical for node "flagged" ring)
    const flagMap = {};
    for (const a of anomalies) {
      if (!a.attestation_id) continue;
      (flagMap[a.attestation_id] ||= []).push(a.type);
    }
    const hashBad = new Set(
      anomalies.filter((a) => a.type === 'parent_hash_mismatch').map((a) => a.attestation_id),
    );

    const { depth, maxD } = computeDepths(atts, leafId);
    // group by column (column 0 = leftmost = deepest raw materials)
    const cols = {};
    atts.forEach((a) => {
      const col = maxD - depth[a.attestation_id];
      (cols[col] ||= []).push(a);
    });

    const nodes = [];
    Object.entries(cols).forEach(([col, list]) => {
      const c = Number(col);
      const offset = (list.length - 1) / 2;
      list.forEach((a, i) => {
        nodes.push({
          id: a.attestation_id,
          type: 'att',
          position: { x: c * COL_W, y: (i - offset) * ROW_H },
          data: {
            att: a,
            isLeaf: a.attestation_id === leafId,
            flags: flagMap[a.attestation_id] || [],
          },
        });
      });
    });

    const edges = [];
    for (const a of atts) {
      for (const p of a.parents || []) {
        if (!p.attestation_id) continue;
        const bad = hashBad.has(a.attestation_id);
        edges.push({
          id: `${p.attestation_id}->${a.attestation_id}`,
          source: p.attestation_id,
          target: a.attestation_id,
          animated: !bad,
          label: p.quantity_consumed != null ? `${p.quantity_consumed} ${p.unit || ''}`.trim() : undefined,
          labelStyle: { fill: '#5b6b8c', fontSize: 11, fontWeight: 600 },
          labelBgStyle: { fill: '#ffffff', fillOpacity: 0.85 },
          style: { stroke: bad ? '#d83434' : '#2f4fb0', strokeWidth: bad ? 2.5 : 1.6, strokeDasharray: bad ? '5 4' : undefined },
          markerEnd: { type: MarkerType.ArrowClosed, color: bad ? '#d83434' : '#2f4fb0' },
        });
      }
    }
    return { nodes, edges };
  }, [atts, leafId, anomalies]);

  if (!atts?.length) return null;

  return (
    <div className="card">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="font-bold text-aegis-deep">Provenance graph</h3>
        <div className="flex items-center gap-3 text-[0.72rem] text-aegis-muted">
          <span className="flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm border-2 border-aegis-green" /> Canada</span>
          <span className="flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm border-2 border-aegis-line" /> Foreign</span>
          <span className="flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm border-2 border-aegis-deep" /> Finished product</span>
          <span className="flex items-center gap-1"><i className="inline-block w-3 h-3 rounded-sm border-2 border-aegis-red" /> Flagged</span>
        </div>
      </div>
      <p className="text-aegis-muted text-xs mb-3">
        Raw materials flow left → right into the finished product. Drag to pan, scroll to zoom.
      </p>
      <div style={{ height: 440 }} className="rounded-xl border border-aegis-line overflow-hidden bg-aegis-bg/40">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="#c7d0e6" gap={20} />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeStrokeWidth={3}
            nodeColor={(n) => n.data?.flags?.length ? '#d83434'
              : n.data?.isLeaf ? '#1f3a8a'
              : n.data?.att?.performed_in_country === 'CA' ? '#1f6b4f' : '#c7d0e6'}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
