#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[gate] Stage 0"
bash scripts/stage0/test_stage0_runtime.sh

echo "[gate] Stage 0.5"
bash scripts/stage0_5/run_tests.sh

echo "[gate] Stage 1A"
if [[ -n "${DATABASE_URL:-}" ]]; then
  bash scripts/stage1a-test.sh
else
  echo "DATABASE_URL not set; running Stage 1A runtime/eval tests only"
  python3 -m unittest \
    tests/stage1a/test_stage1a_slice7_api_workflow.py \
    tests/stage1a/test_stage1a_slice8_evaluation.py
fi

echo "[gate] Stage 1B"
bash scripts/stage1b-test.sh

echo "[gate] Stage 2"
python3 -m unittest discover -s tests/stage2 -p 'test_*.py'

echo "[gate] Stage 3"
python3 -m unittest discover -s tests/stage3 -p 'test_*.py'

echo "[gate] Control Tower"
python3 -m unittest discover -s tests/webapp -p 'test_*.py'
bash scripts/webapp-smoke-test.sh
bash scripts/pilot-smoke-test.sh

echo "[gate] Migration Tooling"
python3 -m unittest tests/db/test_migration_orchestrator.py

echo "All MVP hard gates passed."
