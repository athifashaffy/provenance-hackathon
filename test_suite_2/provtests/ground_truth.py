"""Ground truth, measured from training_corpus.jsonl (1,000 cases).

Single source of truth for every test. Do not invent families or types here —
these are exactly what appears in the labels. See CORPUS_GROUND_TRUTH.md.
"""
from __future__ import annotations

# The only 11 anomaly.type strings that exist in the labels.
ANOMALY_TYPES = {
    "parent_hash_mismatch",
    "timestamp_inversion",
    "signature_invalid",
    "circular_reference",
    "cost_anomaly",
    "transformation_implausible",
    "signature_unknown_supplier",
    "mass_balance_violation",
    "dangling_parent",
    "unit_mismatch",
    "replay_within_chain",
}

# The 4 statistical families: chain_valid stays True, no anomalies[], scored by
# F1 over t4_perturbed ids.
T4_FAMILIES = {
    "t4_timing_outlier",
    "t4_origin_outlier",
    "t4_labour_outlier",
    "t4_cost_outlier",
}

# The 13 hard-rule families: chain_valid False, real anomalies[] entries.
HARD_RULE_FAMILIES = {
    "timestamp_inversion",
    "circular",
    "signature_corrupt",
    "transformation_implausible",
    "unknown_supplier",
    "cost_anomaly",
    "mass_balance",
    "dangling_parent",
    "parent_hash_mismatch",
    "unit_mismatch",
    "replay_within_chain",
    "tamper_no_resign",
}

CLEAN_FAMILY = "clean"

ALL_FAMILIES = {CLEAN_FAMILY} | T4_FAMILIES | HARD_RULE_FAMILIES

# Expected chain_valid by family (measured: every hard-rule False, every T4/clean True).
def expected_chain_valid(family: str) -> bool:
    return family not in HARD_RULE_FAMILIES

# Which anomaly.type(s) each hard-rule family is observed to emit. Multi-node
# families emit several distinct types across several attestations.
FAMILY_TYPES = {
    "signature_corrupt": {"signature_invalid"},
    "unknown_supplier": {"signature_unknown_supplier", "parent_hash_mismatch"},
    "parent_hash_mismatch": {"parent_hash_mismatch"},
    "tamper_no_resign": {"signature_invalid", "parent_hash_mismatch", "cost_anomaly"},
    "timestamp_inversion": {"timestamp_inversion"},
    "circular": {"circular_reference", "parent_hash_mismatch", "timestamp_inversion"},
    "dangling_parent": {"dangling_parent"},
    "unit_mismatch": {"unit_mismatch"},
    "mass_balance": {"mass_balance_violation"},
    "replay_within_chain": {"replay_within_chain"},
    "transformation_implausible": {"transformation_implausible"},
    "cost_anomaly": {"cost_anomaly"},
}

# Designation rules (TECHNICAL_GUIDE §6).
TRANSFORMATIONS = {"component_manufacture", "subassembly", "final_integration"}
SUBSTANTIAL_MIN_HOURS = 4
THRESH_PRODUCT_OF_CANADA = 98
THRESH_MADE_IN_CANADA = 51
VALID_DESIGNATIONS = {"product_of_canada", "made_in_canada", "none"}

# Harness scoring constants (self_test.py).
PCT_TOL = 0.5
PCT_ZERO = 5.0

# Genuine working-hours window for timestamps (measured: clean ts only at UTC 9 and 14).
GENUINE_TS_HOURS = {9, 14}
