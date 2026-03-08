#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000021_stage1a_pipeline_entrypoints.rollback.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000020_stage1a_read_models.rollback.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000019_stage1a_approval_workflow.rollback.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000018_stage1a_event_emit_function.rollback.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000017_stage1a_state_and_event_guards.rollback.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/rollback/000016_stage1a_comment_extraction.rollback.sql

echo "Stage 1A migrations rolled back"
