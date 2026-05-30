// The four verification categories the purchaser sees. Each anomaly type maps
// to exactly one category; we show every category as PASS or with its failures.

export const CATEGORIES = [
  {
    key: 'integrity',
    icon: '🔐',
    title: 'Integrity & identity',
    desc: 'Every signature verifies against the registered supplier key; nothing was altered after signing.',
    types: ['signature_invalid', 'signature_unknown_supplier', 'anchor_mismatch', 'tamper'],
  },
  {
    key: 'structure',
    icon: '🔗',
    title: 'Chain structure',
    desc: 'Hash-linked parents, no missing references, no cycles, no impossible timestamps.',
    types: ['parent_hash_mismatch', 'dangling_parent', 'circular_reference',
            'timestamp_inversion', 'unit_mismatch', 'replay_within_chain',
            'replay_cross_chain', 'transformation_implausible'],
  },
  {
    key: 'mass_balance',
    icon: '⚖️',
    title: 'Mass balance',
    desc: 'No node consumes more material than its upstream suppliers ever produced.',
    types: ['mass_balance_violation'],
  },
  {
    key: 'statistical',
    icon: '📊',
    title: 'Statistical anomalies',
    desc: 'Cost, labour, timing and origin patterns checked against genuine supply chains.',
    types: ['statistical_outlier', 'cost_anomaly'],
    soft: true, // failures here are advisory, not integrity-breaking
  },
];

// Returns [{...category, status:'pass'|'fail'|'flag', findings:[anomaly]}]
export function categorize(anomalies = []) {
  const known = new Set(CATEGORIES.flatMap((c) => c.types));
  return CATEGORIES.map((c) => {
    const findings = anomalies.filter((a) => c.types.includes(a.type));
    let status = 'pass';
    if (findings.length) status = c.soft ? 'flag' : 'fail';
    // catch-all: any unmapped anomaly type lands under chain structure as a fail
    if (c.key === 'structure') {
      const extra = anomalies.filter((a) => !known.has(a.type));
      if (extra.length) { findings.push(...extra); status = 'fail'; }
    }
    return { ...c, status, findings };
  });
}
