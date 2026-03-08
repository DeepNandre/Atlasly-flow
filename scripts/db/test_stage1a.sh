#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/db/migrations"
ROLLBACK_DIR="$ROOT_DIR/db/migrations/rollback"
TESTS_DIR="$ROOT_DIR/tests/stage1a"
FIXTURES_DIR="$ROOT_DIR/db/tests/fixtures"

for cmd in initdb pg_ctl createdb dropdb psql; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing required command: $cmd" >&2
    exit 1
  fi
done

TMP_DIR="$(mktemp -d)"
PGDATA="$TMP_DIR/pgdata"
SOCK_DIR="$TMP_DIR/socket"
PORT=$((20000 + (RANDOM % 10000)))
DB_NAME="stage1a_full"

cleanup() {
  set +e
  if [[ -f "$PGDATA/postmaster.pid" ]]; then
    pg_ctl -D "$PGDATA" -m fast stop >/dev/null 2>&1
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$SOCK_DIR"
initdb -D "$PGDATA" >/dev/null
pg_ctl -D "$PGDATA" -o "-p $PORT -k $SOCK_DIR" -w start >/dev/null
createdb -h "$SOCK_DIR" -p "$PORT" "$DB_NAME"

apply_sql() {
  local file="$1"
  echo "applying: $(basename "$file")"
  psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$file" >/dev/null
}

# Stage 0 minimum for Stage1A FKs and helpers.
apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.up.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.up.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.up.sql"
apply_sql "$FIXTURES_DIR/100_stage0_minimal_for_stage1a_stage1b.sql"

# Stage 1A slices.
apply_sql "$MIGRATIONS_DIR/000016_stage1a_comment_extraction.sql"
apply_sql "$MIGRATIONS_DIR/000017_stage1a_state_and_event_guards.sql"
apply_sql "$MIGRATIONS_DIR/000018_stage1a_event_emit_function.sql"
apply_sql "$MIGRATIONS_DIR/000019_stage1a_approval_workflow.sql"
apply_sql "$MIGRATIONS_DIR/000020_stage1a_read_models.sql"
apply_sql "$MIGRATIONS_DIR/000021_stage1a_pipeline_entrypoints.sql"

echo "running stage1a sql contracts"
for test in \
  20260303_slice1_contract_checks.sql \
  20260303_slice2_state_event_checks.sql \
  20260303_slice3_emit_function_checks.sql \
  20260303_slice4_approve_checks.sql \
  20260303_slice5_read_models_checks.sql \
  20260303_slice6_pipeline_entrypoint_checks.sql; do
  psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/$test" >/dev/null
done

echo "verifying stage1a rollback"
apply_sql "$ROLLBACK_DIR/000021_stage1a_pipeline_entrypoints.rollback.sql"
apply_sql "$ROLLBACK_DIR/000020_stage1a_read_models.rollback.sql"
apply_sql "$ROLLBACK_DIR/000019_stage1a_approval_workflow.rollback.sql"
apply_sql "$ROLLBACK_DIR/000018_stage1a_event_emit_function.rollback.sql"
apply_sql "$ROLLBACK_DIR/000017_stage1a_state_and_event_guards.rollback.sql"
apply_sql "$ROLLBACK_DIR/000016_stage1a_comment_extraction.rollback.sql"

echo "stage1a db tests passed"
