"""
Stateless /verify engine for the Cryptographic Provenance challenge.

Implements the LOCKED spec (provenance-hackathon/spec/*):
  - canonical serialization + Ed25519 verification via the shipped reference_lib
    (byte-exact with the scoring harness — see vendor/reference_lib)
  - canadian_content_percentage + designation (spec/computation.md)
  - integrity anomalies (hard) + statistical outliers (soft, learned from the
    training corpus distribution)

This module is pure and DB-free: verify_chain(submission) -> response dict.
The harness POSTs the full chain in one request, so no persistence is needed.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

from vendor.reference_lib.canonical import content_hash
from vendor.reference_lib.crypto import verify_attestation

# ── Static assets (loaded once) ────────────────────────────────────────────────
_DATA = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA, "supplier_public_keys.json")) as f:
    SUPPLIER_KEYS: dict = json.load(f)["keys"]

with open(os.path.join(_DATA, "anchor_registry.json")) as f:
    _anc = json.load(f)
    ANCHORS: dict = {a["attestation_id"]: a for a in _anc.get("anchors", [])}

with open(os.path.join(_DATA, "stats.json")) as f:
    STATS: dict = json.load(f)

SUPPLIER_COUNTRY = STATS["supplier_country_counts"]
LABOUR_HOURS_MAX = STATS["labour_hours_clean_max"]
LABOUR_RATE_MAX = STATS["labour_rate_clean_max"]
# per-action robust baselines (median + MAD) for statistical outlier z-scores
LABOUR_RATE_ROBUST = STATS.get("labour_rate_robust", {})
LABOUR_HOURS_ROBUST = STATS.get("labour_hours_robust", {})

# Statistical-outlier robust-z cut-offs. Calibrated against the corpus harness
# score (analysis/calibrate.py): the corpus IS the official generator's output,
# so its clean-vs-t4 trade-off is the real held-out predictor. Override via env
# for the calibration sweep.
import os as _os
RATE_Z = float(_os.environ.get("AEGIS_RATE_Z", "2.8"))
HOURS_Z = float(_os.environ.get("AEGIS_HOURS_Z", "2.6"))


def _robust_z(value, baseline):
    if not baseline:
        return None
    mad = baseline.get("mad") or 1e-9
    return (value - baseline["median"]) / (1.4826 * mad)

CA_CODES = {"CA", "CAN", "CANADA"}
TRANSFORM_ACTIONS = {"component_manufacture", "subassembly", "final_integration"}
EPS = 1e-6

# Canonical timestamps observed across every clean chain (used for timing outliers)
CANON_TIME = {"raw_material_supply": "09:00:00Z"}
CANON_TIME_TRANSFORM = "14:30:00Z"

# Plausible labour-rate band (clean corpus is [40, 142] CAD/hr)
RATE_HARD_HI = 180.0
RATE_HARD_LO = 10.0
# Material-cost ceiling: clean corpus material_cad maxes at ~24k; a single line
# item far above that (e.g. 9.9M) is an impossible cost, flag as cost_anomaly.
MATERIAL_HARD_HI = 100000.0

# Anomaly types that invalidate the chain (vs. soft statistical outliers)
HARD_TYPES = {
    "signature_invalid", "signature_unknown_supplier", "parent_hash_mismatch",
    "mass_balance_violation", "circular_reference", "dangling_parent",
    "timestamp_inversion", "unit_mismatch", "replay_within_chain",
    "cost_anomaly", "transformation_implausible", "anchor_mismatch",
    "replay_cross_chain",
}


# ── helpers ─────────────────────────────────────────────────────────────────────
def _is_ca(country) -> bool:
    return isinstance(country, str) and country.strip().upper() in CA_CODES


def _parse_ts(ts):
    if not isinstance(ts, str):
        return None
    s = ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _labour_rate(att):
    c = att.get("costs") or {}
    h = c.get("labour_hours") or 0
    if h and h > 0:
        return (c.get("labour_cost_cad") or 0) / h
    return None


# ── Step 1+2: percentage and designation (spec/computation.md) ─────────────────
def compute_content(cost_atts: list[dict], by_id: dict, product_id: str):
    # percentage is a flat sum over every submitted attestation entry (the spec
    # iterates the submitted list — duplicates from a replay are counted as sent)
    total = 0.0
    canadian = 0.0
    for a in cost_atts:
        c = a.get("costs") or {}
        node_cost = (c.get("material_cad") or 0) + (c.get("labour_cost_cad") or 0)
        total += node_cost
        if _is_ca(a.get("performed_in_country")):
            canadian += node_cost

    if total <= 0:
        return 0.0, "none"
    # clamp to [0,100]: negative/tampered cost components can otherwise push the
    # ratio out of range (the spec percentage is defined as 0-100)
    pct = max(0.0, min(100.0, canadian / total * 100.0))

    # last substantial transformation = qualifying node closest to the leaf
    def qualifies(a):
        return (a.get("action_type") in TRANSFORM_ACTIONS
                and (a.get("costs") or {}).get("labour_hours", 0) >= 4)

    last_st = None
    if product_id in by_id:
        # BFS over parents from the leaf; first qualifying node by hop-distance wins
        seen = {product_id}
        q = deque([product_id])
        while q:
            cur = q.popleft()
            node = by_id.get(cur)
            if node is None:
                continue
            if qualifies(node):
                last_st = node
                break
            for p in node.get("parents") or []:
                pid = p.get("attestation_id")
                if pid and pid not in seen:
                    seen.add(pid)
                    q.append(pid)
    if last_st is None:
        # fall back to any qualifying node in the chain (closest-to-leaf unknowable)
        for a in by_id.values():
            if qualifies(a):
                last_st = a
                break

    if last_st is None or not _is_ca(last_st.get("performed_in_country")):
        designation = "none"
    elif pct >= 98:
        designation = "product_of_canada"
    elif pct >= 51:
        designation = "made_in_canada"
    else:
        designation = "none"

    return round(pct, 2), designation


# ── Step 3: anomaly detection ──────────────────────────────────────────────────
def detect_anomalies(raw_atts: list[dict], by_id: dict, product_id: str) -> list[dict]:
    anomalies: list[dict] = []

    def add(atype, aid, details):
        anomalies.append({"type": atype, "attestation_id": aid, "details": details})

    # replay_within_chain — duplicate attestation_id in the submission
    counts = Counter(a.get("attestation_id") for a in raw_atts)
    for aid, n in counts.items():
        if aid and n > 1:
            add("replay_within_chain", aid, "duplicate attestation_id in submission")

    # precompute content hashes (signature excluded) once
    chash = {}
    for aid, a in by_id.items():
        try:
            chash[aid] = content_hash(a)
        except Exception:
            chash[aid] = None

    for aid, a in by_id.items():
        supplier_id = a.get("supplier_id")
        action = a.get("action_type")
        parents = a.get("parents") or []

        # signature: unknown supplier vs invalid signature
        pubkey = SUPPLIER_KEYS.get(supplier_id)
        if pubkey is None:
            add("signature_unknown_supplier", aid, f"supplier {supplier_id} not in registry")
        elif not verify_attestation(a, pubkey):
            add("signature_invalid", aid, "signature does not verify vs claimed supplier key")

        # transformation_implausible — a transform that consumes nothing, OR a
        # raw material that claims parents, OR an unknown action_type. (In the
        # corpus, raw_material_supply-with-parents is anomalous 19/19.)
        if action in TRANSFORM_ACTIONS and len(parents) == 0:
            add("transformation_implausible", aid, f"{action} consumes nothing")
        elif action == "raw_material_supply" and len(parents) > 0:
            add("transformation_implausible", aid, "raw_material_supply must not consume inputs")
        elif action not in TRANSFORM_ACTIONS and action != "raw_material_supply":
            add("transformation_implausible", aid, f"unknown action_type {action!r}")

        # cost_anomaly — implausibly high labour rate (clean tops out ~142 CAD/hr).
        # Only an UPPER bound: a low/zero rate is legitimate on zero-cost
        # (insufficient_data) chains, so flagging rate<lo false-positives there.
        rate = _labour_rate(a)
        if rate is not None and rate > RATE_HARD_HI:
            add("cost_anomaly", aid, f"labour rate {round(rate, 1)} CAD/hr outside band")
        # negative / impossible numeric values are never legitimate (corpus is
        # all non-negative). Covers costs, labour_hours, and output quantity.
        costs = a.get("costs") or {}
        out = a.get("output") or {}
        neg = (
            (costs.get("material_cad") or 0) < 0
            or (costs.get("labour_cost_cad") or 0) < 0
            or (costs.get("labour_hours") or 0) < 0
            or (out.get("quantity_produced") or 0) < 0
            or any((p.get("quantity_consumed") or 0) < 0 for p in parents)
        )
        if neg:
            add("cost_anomaly", aid, "negative numeric value")
        # impossibly large material cost (clean tops out ~24k CAD)
        elif (costs.get("material_cad") or 0) > MATERIAL_HARD_HI:
            add("cost_anomaly", aid, f"material cost {costs.get('material_cad')} CAD implausibly high")

        # per-parent checks
        my_ts = _parse_ts(a.get("timestamp"))
        for p in parents:
            pid = p.get("attestation_id")
            parent = by_id.get(pid)
            if parent is None:
                add("dangling_parent", aid, f"parent {pid} not in submission")
                continue
            # parent_hash_mismatch — link must bind to parent's real content
            if chash.get(pid) is not None and p.get("content_hash") != chash[pid]:
                add("parent_hash_mismatch", aid, f"content_hash mismatch for parent {pid}")
            # unit_mismatch — consumed unit must equal parent's output unit
            pout = (parent.get("output") or {}).get("unit")
            if p.get("unit") is not None and pout is not None and p.get("unit") != pout:
                add("unit_mismatch", aid, f"consumes {p.get('unit')} but parent outputs {pout}")
            # timestamp_inversion — child cannot precede its parent
            p_ts = _parse_ts(parent.get("timestamp"))
            if my_ts and p_ts and my_ts < p_ts:
                add("timestamp_inversion", aid, "child timestamp precedes parent")

        # anchor registry checks (never fires on unanchored/new products)
        if aid in ANCHORS:
            rec = ANCHORS[aid]
            if chash.get(aid) is not None and chash[aid] != rec.get("content_hash"):
                add("anchor_mismatch", aid, "content_hash differs from anchored value")
            elif rec.get("product_id") and rec["product_id"] != product_id:
                add("replay_cross_chain", aid,
                    f"anchored to product {rec['product_id']}, submitted under {product_id}")

    # circular_reference — any cycle in the parent graph is attributed to the
    # product leaf (matches the labeler: one entry on product_attestation_id)
    if _find_cycle_nodes(by_id):
        add("circular_reference", product_id, "cycle detected in parent references")

    # mass_balance_violation — global per-node over-consumption
    consumed = defaultdict(float)
    for a in by_id.values():
        for p in a.get("parents") or []:
            pid = p.get("attestation_id")
            if pid in by_id:
                consumed[pid] += p.get("quantity_consumed") or 0
    for pid, used in consumed.items():
        produced = (by_id[pid].get("output") or {}).get("quantity_produced")
        if produced is not None and used > produced + EPS:
            add("mass_balance_violation", pid,
                f"consumed {used} > produced {produced}")

    return anomalies


def _find_cycle_nodes(by_id: dict) -> set:
    """Return the back-edge target of each cycle along parent edges.

    When a parent edge u -> v closes a cycle (v is an ancestor still on the DFS
    stack), v is the node "re-entered" — the labeler attributes the cycle to that
    single node, not to every member of the loop.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in by_id}
    targets = set()

    def dfs(u, stack):
        color[u] = GRAY
        stack.append(u)
        for p in by_id[u].get("parents") or []:
            v = p.get("attestation_id")
            if v not in by_id:
                continue
            if color[v] == GRAY:
                targets.add(v)  # back-edge target
            elif color[v] == WHITE:
                dfs(v, stack)
        stack.pop()
        color[u] = BLACK

    for n in by_id:
        if color[n] == WHITE:
            dfs(n, [])
    return targets


# ── statistical (soft) outliers — only when the chain is otherwise clean ───────
def detect_outliers(unique_atts: list[dict]) -> list[dict]:
    out = []

    def add(aid, details):
        out.append({"type": "statistical_outlier", "attestation_id": aid, "details": details})

    for a in unique_atts:
        aid = a["attestation_id"]
        action = a.get("action_type")
        ts = a.get("timestamp") or ""
        country = a.get("performed_in_country")
        c = a.get("costs") or {}

        # timing outlier — non-canonical time-of-day (0 FP on clean corpus)
        time_part = ts.split("T")[1] if "T" in ts else ""
        canon = CANON_TIME.get(action, CANON_TIME_TRANSFORM)
        if time_part and time_part != canon:
            add(aid, f"non-canonical timestamp {ts}")
            continue

        # origin outlier — raw material claimed CA from a normally-foreign supplier
        if action == "raw_material_supply" and _is_ca(country):
            counts = SUPPLIER_COUNTRY.get(a.get("supplier_id"))
            if counts:
                tot = sum(counts.values())
                ca = counts.get("CA", 0)
                if tot >= 5 and ca / tot < 0.05:
                    add(aid, "raw-material origin CA implausible for this supplier")
                    continue

        # labour-hours outlier — robust z vs the per-action genuine baseline.
        # "Is this an unreasonable amount of labour for THIS kind of step?"
        hrs = c.get("labour_hours") or 0
        if hrs > 0:
            zh = _robust_z(hrs, LABOUR_HOURS_ROBUST.get(action))
            if zh is not None and zh > HOURS_Z:
                add(aid, f"labour_hours {hrs} unreasonable for {action} (z={round(zh,1)})")
                continue

        # cost outlier — robust z of the labour RATE vs the per-action baseline.
        # "Is this a reasonable price for THIS kind of work?" The genuine rate
        # bands overlap across action types, so a flat ceiling can't separate the
        # attack band (97-117 CAD/hr) from genuine; a per-action robust-z tracks
        # each action's own tail. Threshold calibrated on the corpus harness score.
        r = _labour_rate(a)
        if r is not None:
            zr = _robust_z(r, LABOUR_RATE_ROBUST.get(action))
            if zr is not None and zr > RATE_Z:
                add(aid, f"labour rate {round(r, 1)} CAD/hr unreasonable for {action} (z={round(zr,1)})")
                continue

    return out


# ── public entry point ─────────────────────────────────────────────────────────
def verify_chain(submission: dict) -> dict:
    if not isinstance(submission, dict):
        submission = {}
    product_id = submission.get("product_attestation_id")
    raw_in = submission.get("attestations")
    # "handle incomplete data without falling over": tolerate a non-list
    # attestations field and drop any entry that isn't a dict, so a single
    # malformed attestation can never 500 the whole request.
    raw_atts = [a for a in raw_in if isinstance(a, dict)] if isinstance(raw_in, list) else []

    # dedup by attestation_id (first occurrence wins) for cost + structure
    by_id: dict = {}
    for a in raw_atts:
        aid = a.get("attestation_id")
        if aid and aid not in by_id:
            by_id[aid] = a
    unique_atts = list(by_id.values())

    pct, designation = compute_content(raw_atts, by_id, product_id)

    anomalies = detect_anomalies(raw_atts, by_id, product_id)
    hard = [a for a in anomalies if a["type"] in HARD_TYPES]
    chain_valid = len(hard) == 0

    # statistical outliers only when the chain has no hard integrity violation
    # (the two are mutually exclusive in the corpus; this protects precision)
    if chain_valid:
        anomalies.extend(detect_outliers(unique_atts))

    return {
        "product_attestation_id": product_id,
        "canadian_content_percentage": pct,
        "designation": designation,
        "chain_valid": chain_valid,
        "anomalies": anomalies,
    }


# ── Self-scorecard ──────────────────────────────────────────────────────────────
# `python verify.py [corpus.jsonl]` grades the in-process engine against the
# labelled corpus and prints the harness score + an F1 breakdown (hard / t4 /
# all non-clean) and clean over-flagging. Defaults to ../training_corpus.jsonl.
def _score_corpus(corpus_path: str) -> dict:
    PCT_TOL, PCT_ZERO = 0.5, 5.0

    def ids_by(anoms):
        d = {}
        for a in anoms or []:
            d.setdefault(a.get("attestation_id"), set()).add(a.get("type"))
        return d

    def case_score(kind, exp, t4, resp):
        if kind.startswith("t4_"):
            truth = set(t4); fl = {a.get("attestation_id") for a in resp.get("anomalies", [])}
            tp = len(truth & fl); pr = tp/len(fl) if fl else 0.0; rc = tp/len(truth) if truth else 1.0
            return 2*pr*rc/(pr+rc) if (pr+rc) else 0.0
        try:
            diff = abs(float(resp.get("canadian_content_percentage", -999)) - exp["canadian_content_percentage"])
        except (TypeError, ValueError):
            diff = 1e9
        pct = 1.0 if diff <= PCT_TOL else max(0.0, 1-(diff-PCT_TOL)/(PCT_ZERO-PCT_TOL))
        desig = 1.0 if resp.get("designation") == exp["designation"] else 0.0
        em, rm = ids_by(exp["anomalies"]), ids_by(resp.get("anomalies"))
        ei, ri = set(em), set(rm); tp = ei & ri
        if not ei and not ri: f1 = 1.0
        elif not ei or not ri: f1 = 0.0
        else:
            p, r = len(tp)/len(ri), len(tp)/len(ei); f1 = 2*p*r/(p+r) if (p+r) else 0.0
        cl = (sum(1 for i in tp if em[i] & rm[i])/len(tp)) if tp else (1.0 if not ei else 0.0)
        return 0.30*pct + 0.35*f1 + 0.20*desig + 0.15*cl

    rows = [json.loads(l) for l in open(corpus_path)]
    total = 0.0
    bycat = defaultdict(lambda: [0.0, 0])
    hard_tp = hard_fp = hard_fn = 0
    t4_tp = t4_fp = t4_fn = 0
    clean_overflag = 0
    for row in rows:
        lab = row["labels"]; kind = lab.get("attack", "clean"); t4 = lab.get("t4_perturbed", [])
        resp = verify_chain(json.loads(json.dumps(row["chain"])))
        s = case_score(kind, lab, t4, resp); total += s
        bycat[kind][0] += s; bycat[kind][1] += 1
        flagged = {a["attestation_id"] for a in resp.get("anomalies", [])}
        if kind == "clean":
            if flagged: clean_overflag += 1
        elif kind.startswith("t4_"):
            truth = set(t4)
            t4_tp += len(truth & flagged); t4_fn += len(truth - flagged); t4_fp += len(flagged - truth)
        else:
            truth = {a["attestation_id"] for a in lab["anomalies"]}
            hard_tp += len(truth & flagged); hard_fn += len(truth - flagged); hard_fp += len(flagged - truth)
    return {"rows": rows, "total": total, "bycat": bycat,
            "hard": (hard_tp, hard_fp, hard_fn), "t4": (t4_tp, t4_fp, t4_fn),
            "clean_overflag": clean_overflag}


def _f1(tp, fp, fn):
    p = tp/(tp+fp) if (tp+fp) else 0.0
    r = tp/(tp+fn) if (tp+fn) else 0.0
    return p, r, (2*p*r/(p+r) if (p+r) else 0.0)


if __name__ == "__main__":
    import sys
    corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "training_corpus.jsonl")
    res = _score_corpus(corpus)
    n = len(res["rows"])
    print(f"\noverall: {res['total']/n*100:.1f}%  ({n} cases)   [RATE_Z={RATE_Z} HOURS_Z={HOURS_Z}]\n")
    print(f"{'category':28s}  avg     n")
    for k in sorted(res["bycat"]):
        v = res["bycat"][k]
        print(f"{k:28s}  {v[0]/v[1]*100:5.1f}  {v[1]:4d}")
    hp, hr, hf = _f1(*res["hard"]); tp_, tr, tf = _f1(*res["t4"])
    allf = _f1(res["hard"][0]+res["t4"][0], res["hard"][1]+res["t4"][1], res["hard"][2]+res["t4"][2])
    cof = res["clean_overflag"]
    print(f"\nanomaly-detection F1 (micro over attestation_ids):")
    print(f"{'group':22s} prec   recall  f1     tp/fp/fn")
    print(f"{'hard (rule-based)':22s} {hp:.3f}  {hr:.3f}  {hf:.3f}  {res['hard'][0]}/{res['hard'][1]}/{res['hard'][2]}")
    print(f"{'t4 (statistical)':22s} {tp_:.3f}  {tr:.3f}  {tf:.3f}  {res['t4'][0]}/{res['t4'][1]}/{res['t4'][2]}")
    print(f"{'all non-clean':22s} {allf[0]:.3f}  {allf[1]:.3f}  {allf[2]:.3f}  "
          f"{res['hard'][0]+res['t4'][0]}/{res['hard'][1]+res['t4'][1]}/{res['hard'][2]+res['t4'][2]}")
    print(f"clean over-flagging: {cof}/705 cases ({cof/705*100:.1f}%)")
