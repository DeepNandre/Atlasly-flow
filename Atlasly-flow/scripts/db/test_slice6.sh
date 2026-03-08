#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/db/migrations"
TESTS_DIR="$ROOT_DIR/db/tests"

for cmd in initdb pg_ctl createdb psql; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing required command: $cmd" >&2
    exit 1
  fi
done

TMP_DIR="$(mktemp -d)"
PGDATA="$TMP_DIR/pgdata"
SOCK_DIR="$TMP_DIR/socket"
PORT=$((20000 + (RANDOM % 10000)))
DB_NAME="stage0_slice6"

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

apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.up.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.up.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.up.sql"
apply_sql "$MIGRATIONS_DIR/000004_stage0_core_domain.up.sql"
apply_sql "$MIGRATIONS_DIR/000005_stage0_documents_and_versions.up.sql"
apply_sql "$MIGRATIONS_DIR/000006_stage0_audit_and_domain_events.up.sql"
apply_sql "$MIGRATIONS_DIR/000007_stage0_notifications.up.sql"
apply_sql "$MIGRATIONS_DIR/000008_stage0_rls_policies.up.sql"

echo "running contract tests: 001..006"
for test in \
  001_slice1_contracts.sql \
  002_slice2_core_domain_contracts.sql \
  003_slice3_documents_contracts.sql \
  004_slice4_events_contracts.sql \
  005_slice5_notifications_contracts.sql \
  006_slice6_rls_contracts.sql; do
  psql -v ON_ERROR_STOP=1 -h "$SOCK_DIR" -p "$PORT" -d "$DB_NAME" -f "$TESTS_DIR/$test" >/dev/null
done

echo "verifying down migrations"
apply_sql "$MIGRATIONS_DIR/000008_stage0_rls_policies.down.sql"
apply_sql "$MIGRATIONS_DIR/000007_stage0_notifications.down.sql"
apply_sql "$MIGRATIONS_DIR/000006_stage0_audit_and_domain_events.down.sql"
apply_sql "$MIGRATIONS_DIR/000005_stage0_documents_and_versions.down.sql"
apply_sql "$MIGRATIONS_DIR/000004_stage0_core_domain.down.sql"
apply_sql "$MIGRATIONS_DIR/000003_stage0_identity_and_tenancy.down.sql"
apply_sql "$MIGRATIONS_DIR/000002_stage0_create_types.down.sql"
apply_sql "$MIGRATIONS_DIR/000001_stage0_enable_extensions.down.sql"

echo "slice6 tests passed"

