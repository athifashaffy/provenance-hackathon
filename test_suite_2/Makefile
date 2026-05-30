# Provenance verifier test suite
PY ?= python3
BACKEND_URL ?= http://localhost:8000/verify

.PHONY: help install test offline live bdd corpus oracle t4 clean

help:
	@echo "make install   - install deps (pytest, pytest-bdd, cryptography, requests)"
	@echo "make test      - run everything that needs no server (offline)"
	@echo "make offline   - alias for test"
	@echo "make bdd       - run the corpus-grounded BDD scenarios"
	@echo "make oracle    - run the reference-oracle TDD tests"
	@echo "make t4        - run the statistical-detector tests"
	@echo "make live      - run live tests against BACKEND_URL=$(BACKEND_URL)"
	@echo "make clean     - remove caches"

install:
	$(PY) -m pip install -r requirements.txt

test offline:
	$(PY) -m pytest -m "not live"

bdd:
	$(PY) -m pytest tests/test_groundtruth_bdd.py -v

oracle:
	$(PY) -m pytest tests/test_reference_oracle.py -v

t4:
	$(PY) -m pytest tests/test_t4_detector.py -v

live:
	BACKEND_URL=$(BACKEND_URL) $(PY) -m pytest -m live -v

clean:
	rm -rf .pytest_cache .cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
