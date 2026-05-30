"""ADAPTERS - wire the suite to YOUR backend / implementation.

By default the suite grades the bundled reference verifier (no server needed).
Two ways to test your own system instead:

1. LIVE backend (recommended): run your Docker Compose stack, then
       BACKEND_URL=http://localhost:8000/verify pytest -m live
   The live tests in tests/test_verify_contract.py and the corpus regression
   will hit your /verify.

2. IN-PROCESS: point these shims at your Python implementation and the
   corpus-grounded TDD/BDD tests will grade your functions directly.
"""
from __future__ import annotations

import os

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/verify")

# In-process shims default to the reference implementation. Repoint to yours:
from provtests import reference_verifier as _ref

verify_chain = _ref.verify_chain
compute_percentage = _ref.compute_percentage
compute_designation = _ref.compute_designation
detect_hard_rule_anomalies = _ref.detect_hard_rule_anomalies

# --- Compatibility shims for the spec-only unit tests --------------------
# These early TDD tests (test_percentage/designation/mass_balance) assert pure
# functions. Default them to the reference_logic spec oracle. Repoint to your
# implementation to grade your maths directly.
from provtests import reference_logic as _refl

find_mass_balance_violations = _refl.find_mass_balance_violations
direct_cost = _refl.direct_cost
# compute_percentage / compute_designation already exported above from
# reference_verifier; reference_logic versions are equivalent on the spec.
