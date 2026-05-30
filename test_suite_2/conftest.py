"""Root conftest: makes `provtests` importable from anywhere and defines fixtures.

Placed at the project root so `pytest` discovers it before collecting tests. It
inserts the project root on sys.path, so `from provtests import ...` works
whether you run `pytest`, `pytest tests/`, or invoke from a parent directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

# Point the corpus loader at the bundled data unless overridden.
os.environ.setdefault("CORPUS_PATH", str(ROOT / "data" / "training_corpus.jsonl"))


def pytest_addoption(parser):
    parser.addoption("--limit", action="store", type=int, default=0,
                     help="limit corpus regression to first N cases")
    parser.addoption("--backend-url", action="store", default=None,
                     help="override BACKEND_URL for live tests")


@pytest.fixture
def corpus_limit(request) -> int:
    return request.config.getoption("--limit")


@pytest.fixture(scope="session")
def backend_url(request) -> str:
    return (request.config.getoption("--backend-url")
            or os.environ.get("BACKEND_URL", "http://localhost:8000/verify"))


@pytest.fixture(scope="session")
def corpus_path() -> Path:
    p = ROOT / "data" / "training_corpus.jsonl"
    if not p.exists():
        pytest.skip(f"missing corpus at {p}")
    return p


@pytest.fixture(scope="session")
def verify_client(backend_url):
    """callable(payload)->json against a live backend. Skips if unreachable."""
    requests = pytest.importorskip("requests")

    def _call(payload, timeout=10):
        r = requests.post(backend_url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()

    try:
        requests.post(backend_url,
                      json={"product_attestation_id": "att-probe", "attestations": []},
                      timeout=3)
    except Exception as e:
        pytest.skip(f"backend not reachable at {backend_url}: {e}")
    return _call


@pytest.fixture(scope="session")
def worked_example():
    """Optional worked-example files if you drop them in data/. Skips otherwise."""
    import json
    chain = ROOT / "data" / "recovery_drone_chain.json"
    exp = ROOT / "data" / "recovery_drone_expected.json"
    if not (chain.exists() and exp.exists()):
        pytest.skip("worked-example files not in data/")
    return json.loads(chain.read_text()), json.loads(exp.read_text())
