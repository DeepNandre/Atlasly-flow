#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/db/migrations"
TESTS_DIR="$ROOT_DIR/db/tests"

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
DB_NAME="stage0_5_slice3"

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

# Stage 0 base.
apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.up.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.up.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.up.sql"

# Stage 0.5 slices.
apply_sql "$MIGRATIONS_DIR/000010_stage0_5_enterprise_readiness.up.sql"
apply_sql "$MIGRATIONS_DIR/000011_stage0_5_webhook_control_plane.up.sql"
apply_sql "$MIGRATIONS_DIR/000012_stage0_5_webhook_delivery_runtime.up.sql"

echo "running contract tests"
psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/001_slice1_contracts.sql" >/dev/null
psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/002_stage0_5_webhook_control_plane.sql" >/dev/null
psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/003_stage0_5_webhook_delivery_runtime.sql" >/dev/null

# verify rollback path for this slice
apply_sql "$MIGRATIONS_DIR/000012_stage0_5_webhook_delivery_runtime.down.sql"
apply_sql "$MIGRATIONS_DIR/000011_stage0_5_webhook_control_plane.down.sql"
apply_sql "$MIGRATIONS_DIR/000010_stage0_5_enterprise_readiness.down.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.down.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.down.sql"
apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.down.sql"

echo "slice3 stage0.5 tests passed"
