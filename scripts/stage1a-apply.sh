#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000016_stage1a_comment_extraction.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000017_stage1a_state_and_event_guards.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000018_stage1a_event_emit_function.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000019_stage1a_approval_workflow.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000020_stage1a_read_models.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/000021_stage1a_pipeline_entrypoints.sql

echo "Stage 1A migrations applied"
