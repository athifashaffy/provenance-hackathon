"""
Canadian content percentage computation.

Rules (Competition Bureau):
  Product of Canada  >= 98% of total direct costs + last substantial transformation in CA
  Made in Canada     >= 51% of total direct costs + last substantial transformation in CA

Costs are aggregated across ALL tiers of the DAG.
Only costs from leaf-level materials and labour are counted
(to avoid double-counting when intermediate attestations reference upstream costs).

Strategy: a node's direct costs are its OWN materials + labour ONLY.
          Upstream costs flow through via the DAG traversal.
"""

CANADA_CODES = {"CA", "CAN", "CANADA"}


def is_canadian(country: str) -> bool:
    return country.strip().upper() in CANADA_CODES


def compute_content(chain_nodes: list[dict]) -> dict:
    """
    Given a list of attestation records from traverse_dag, compute:
    - total_cost_cad
    - canadian_cost_cad
    - canadian_content_pct
    - designation
    - last_transformation_in_canada
    """
    seen_ids = set()
    total_cost = 0.0
    canadian_cost = 0.0
    last_transformation_in_canada = False

    if not chain_nodes:
        return {
            "total_cost_cad": 0.0,
            "canadian_cost_cad": 0.0,
            "canadian_content_pct": 0.0,
            "designation": "Unknown",
            "last_transformation_in_canada": False,
            "cost_breakdown": [],
        }

    breakdown = []
    # Identify the last substantial transformation node.
    # chain_nodes is pre-order DFS (root first), so earlier = closer to final product.
    # A "substantial transformation" changes the form/nature of inputs:
    #   - Node must have inputs (not a raw material)
    #   - Prefer nodes with an explicit transformation_description
    # The first qualifying node in chain order is the "last" transformation step.
    # The queried attestation is the root (index 0 in pre-order DFS) and IS the
    # final product, so its location is where the last substantial transformation
    # occurred.  The previous heuristic only accepted a node that had upstream
    # attestation `inputs`, which wrongly classified single-tier Canadian products
    # (own materials + labour, no upstream attestation refs) as having NO
    # transformation at all — forcing "Not Qualified" even at 100% Canadian
    # content, and contradicting the seed_edge_cases expectations (EC-01/03/05).
    last_transformation_node = chain_nodes[0]

    # `... or {}` — a present-but-null location ({"location": None}) returns None
    # from .get(default), which would crash on .get("country"). Guard it.
    loc = last_transformation_node["payload"].get("location") or {}
    last_transformation_in_canada = is_canadian(loc.get("country", ""))

    for record in chain_nodes:
        att_id = record["id"]
        if att_id in seen_ids:
            continue
        seen_ids.add(att_id)

        payload = record["payload"]
        materials = payload.get("materials") or []   # null-safe (key may be present-but-null)
        labour = payload.get("labour") or {}
        location = payload.get("location") or {}

        node_total = 0.0
        node_canadian = 0.0

        # Materials
        for mat in materials:
            cost = float(mat.get("cost_cad", 0))
            country = mat.get("country", "")
            node_total += cost
            if is_canadian(country):
                node_canadian += cost
            breakdown.append({
                "attestation_id": att_id,
                "type": "material",
                "name": mat.get("name", ""),
                "cost_cad": cost,
                "country": country,
                "is_canadian": is_canadian(country),
            })

        # Labour
        if labour:
            cost = float(labour.get("cost_cad", 0))
            country = labour.get("country", "")
            node_total += cost
            if is_canadian(country):
                node_canadian += cost
            breakdown.append({
                "attestation_id": att_id,
                "type": "labour",
                "name": "Labour",
                "cost_cad": cost,
                "country": country,
                "is_canadian": is_canadian(country),
            })

        total_cost += node_total
        canadian_cost += node_canadian

    pct = (canadian_cost / total_cost * 100) if total_cost > 0 else 0.0

    if last_transformation_in_canada and pct >= 98.0:
        designation = "Product of Canada"
    elif last_transformation_in_canada and pct >= 51.0:
        designation = "Made in Canada"
    else:
        designation = "Not Qualified"

    return {
        "total_cost_cad": round(total_cost, 2),
        "canadian_cost_cad": round(canadian_cost, 2),
        "canadian_content_pct": round(pct, 2),
        "designation": designation,
        "last_transformation_in_canada": last_transformation_in_canada,
        "cost_breakdown": breakdown,
    }
