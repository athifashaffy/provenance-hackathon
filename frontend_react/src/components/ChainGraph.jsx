// Visual provenance graph: lays attestations out by tier (depth from the leaf)
// and draws the consume-links between them. Leaf (finished product) on the right.

function buildTiers(atts, leafId) {
  const byId = Object.fromEntries(atts.map((a) => [a.attestation_id, a]));
  // depth = longest path from leaf down to this node (so raws sit at the far tier)
  const depth = {};
  function walk(id, d, seen) {
    if (!byId[id] || seen.has(id)) return;
    seen.add(id);
    depth[id] = Math.max(depth[id] ?? 0, d);
    for (const p of byId[id].parents || []) walk(p.attestation_id, d + 1, seen);
    seen.delete(id);
  }
  walk(leafId, 0, new Set());
  // any node never reached (shouldn't happen) gets the deepest tier
  const maxD = Math.max(0, ...Object.values(depth));
  atts.forEach((a) => { if (depth[a.attestation_id] == null) depth[a.attestation_id] = maxD; });
  const tiers = [];
  for (const a of atts) {
    const d = depth[a.attestation_id];
    (tiers[d] ||= []).push(a);
  }
  // render leftmost = deepest (raw materials), rightmost = leaf
  return tiers.map((t) => t || []).reverse();
}

const ACTION_SHORT = {
  raw_material_supply: 'raw',
  component_manufacture: 'component',
  subassembly: 'subassembly',
  final_integration: 'final',
};

export default function ChainGraph({ atts, leafId }) {
  if (!atts?.length) return null;
  const tiers = buildTiers(atts, leafId);

  return (
    <div className="card">
      <h3 className="font-bold text-aegis-deep mb-1">Provenance graph</h3>
      <p className="text-aegis-muted text-xs mb-4">Raw materials on the left flow right into the finished product. Green = performed in Canada.</p>
      <div className="overflow-x-auto">
        <div className="flex items-stretch gap-3 min-w-max pb-2">
          {tiers.map((tier, ti) => (
            <div key={ti} className="flex items-center gap-3">
              <div className="flex flex-col gap-3 justify-center">
                {tier.map((a) => {
                  const ca = a.performed_in_country === 'CA';
                  const isLeaf = a.attestation_id === leafId;
                  return (
                    <div key={a.attestation_id}
                      className={`rounded-xl border-2 px-3 py-2 w-44 ${
                        isLeaf ? 'bg-aegis-blue text-white border-aegis-blue'
                        : ca ? 'bg-white border-aegis-green' : 'bg-white border-aegis-line'}`}>
                      <div className={`font-display font-bold text-sm leading-tight ${isLeaf ? 'text-white' : 'text-aegis-deep'}`}>
                        {a.output?.name || a.attestation_id.slice(0, 10)}
                      </div>
                      <div className={`text-[0.7rem] mt-0.5 ${isLeaf ? 'text-white/80' : 'text-aegis-muted'}`}>
                        {ACTION_SHORT[a.action_type] || a.action_type} · {a.performed_in_country}
                      </div>
                    </div>
                  );
                })}
              </div>
              {ti < tiers.length - 1 && (
                <div className="text-aegis-blue text-xl font-bold self-center">→</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
