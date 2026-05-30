"""Load and index training_corpus.jsonl. Pure stdlib."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[1] / "data" / "training_corpus.jsonl"


def corpus_path() -> Path:
    return Path(os.environ.get("CORPUS_PATH", _DEFAULT))


@lru_cache(maxsize=4)
def load(limit: int = 0) -> tuple:
    p = corpus_path()
    rows = []
    with open(p) as fh:
        for i, line in enumerate(fh):
            if limit and i >= limit:
                break
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return tuple(rows)


def family_of(row: dict) -> str:
    return row["labels"].get("attack", "clean")


def by_family(family: str, limit: int = 0) -> list:
    return [r for r in load(limit) if family_of(r) == family]


def group_by_family(limit: int = 0) -> dict:
    out = defaultdict(list)
    for r in load(limit):
        out[family_of(r)].append(r)
    return dict(out)


def attestations(row: dict) -> list:
    return row["chain"]["attestations"]


def leaf_id(row: dict) -> str:
    return row["chain"]["product_attestation_id"]


def expected_anomaly_ids(row: dict) -> set:
    return {a["attestation_id"] for a in (row["labels"].get("anomalies") or [])}


def expected_anomaly_types(row: dict) -> dict:
    d = defaultdict(set)
    for a in row["labels"].get("anomalies") or []:
        d[a["attestation_id"]].add(a.get("type"))
    return dict(d)


def t4_ids(row: dict) -> set:
    return set(row["labels"].get("t4_perturbed") or [])


@lru_cache(maxsize=1)
def genuine_distributions() -> dict:
    """Per-action_type cost/hours samples and per-supplier country counts,
    built from CLEAN cases only. Used by the T4 statistical detector and tests."""
    cost = defaultdict(list)
    hours = defaultdict(list)
    supplier_country = defaultdict(lambda: defaultdict(int))
    for r in load():
        if family_of(r) != "clean":
            continue
        for a in attestations(r):
            at = a["action_type"]
            c = a["costs"]
            cost[at].append(c.get("material_cad", 0.0) + c.get("labour_cost_cad", 0.0))
            hours[at].append(c.get("labour_hours", 0.0))
            supplier_country[a["supplier_id"]][a["performed_in_country"]] += 1
    return {
        "cost": {k: v for k, v in cost.items()},
        "hours": {k: v for k, v in hours.items()},
        "supplier_country": {k: dict(v) for k, v in supplier_country.items()},
    }
