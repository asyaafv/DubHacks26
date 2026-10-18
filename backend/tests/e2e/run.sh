#!/bin/sh
# Run from this testing worktree. No dependency installation, DDL outside test
# schemas, production wiring changes, or existing encryption-key replacement.
set -eu
: "${TEST_DATABASE_URL:?Supply a disposable Postgres database URL}"
: "${LAPSE_MODEL_CACHE:?Supply the cached pinned MiniLM directory}"
PYTHON=${PYTHON:-python}
export RUN_SEMANTIC_TESTS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec "$PYTHON" -m pytest \
  backend/tests/e2e \
  backend/tests/test_storage_wallet.py \
  backend/tests/test_stacking.py \
  backend/tests/test_lookup_ranking.py \
  backend/tests/test_lookup_semantic.py \
  backend/tests/test_delivery.py \
  backend/tests/test_savings.py \
  -q -rA --tb=short "$@"
