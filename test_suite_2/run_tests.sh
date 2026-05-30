#!/usr/bin/env bash
# One-shot runner. Usage:
#   ./run_tests.sh                 # offline suite (no server)
#   ./run_tests.sh live            # live suite against $BACKEND_URL
#   BACKEND_URL=http://host:8000/verify ./run_tests.sh live
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-offline}"
if ! python3 -c "import pytest" 2>/dev/null; then
  echo "Installing dependencies..."
  python3 -m pip install -r requirements.txt
fi
if [ "$MODE" = "live" ]; then
  : "${BACKEND_URL:=http://localhost:8000/verify}"
  echo "Running LIVE tests against $BACKEND_URL"
  BACKEND_URL="$BACKEND_URL" python3 -m pytest -m live -v
else
  echo "Running OFFLINE suite (reference verifier + corpus, no server needed)"
  python3 -m pytest -m "not live" -v
fi
