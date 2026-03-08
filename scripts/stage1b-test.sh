#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest \
  tests/stage1b/test_stage1b_slice1_contracts.py \
  tests/stage1b/test_stage1b_slice2_api_contracts.py \
  tests/stage1b/test_stage1b_slice3_ticketing_service.py \
  tests/stage1b/test_stage1b_slice4_routing_scheduler.py \
  tests/stage1b/test_stage1b_slice5_workflow_notifications_kpis.py \
  tests/stage1b/test_stage1b_slice6_runtime_api.py \
  tests/stage1b/test_stage1b_slice7_persistence_runtime.py \
  tests/stage1b/test_stage1b_slice8_event_envelope_compliance.py

if [[ -n "${DATABASE_URL:-}" ]]; then
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/tests/002_stage1b_contracts.sql
else
  echo "DATABASE_URL not set; skipped direct SQL contract check"
fi

echo "Stage 1B tests passed"
