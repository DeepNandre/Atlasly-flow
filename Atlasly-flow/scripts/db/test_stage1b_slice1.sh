#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/db/migrations"
ROLLBACK_DIR="$ROOT_DIR/db/migrations/rollback"
TESTS_DIR="$ROOT_DIR/db/tests"
FIXTURES_DIR="$TESTS_DIR/fixtures"

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
DB_NAME="stage1b_slice1"

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

# Stage 0 foundations needed for Stage 1A/1B tests.
apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.up.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.up.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.up.sql"
apply_sql "$FIXTURES_DIR/100_stage0_minimal_for_stage1a_stage1b.sql"

# Stage 1A prerequisite for extraction approvals.
apply_sql "$MIGRATIONS_DIR/000016_stage1a_comment_extraction.sql"

# Stage 1B under test.
apply_sql "$MIGRATIONS_DIR/000022_stage1b_ticketing_routing.sql"

echo "running contract test: 002_stage1b_contracts.sql"
psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/002_stage1b_contracts.sql" >/dev/null

echo "verifying stage1b rollback"
apply_sql "$ROLLBACK_DIR/000022_stage1b_ticketing_routing.rollback.sql"

echo "stage1b slice1 tests passed"
