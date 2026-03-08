#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UP_SQL="$ROOT_DIR/db/migrations/000010_stage0_5_enterprise_readiness.up.sql"
DOWN_SQL="$ROOT_DIR/db/migrations/000010_stage0_5_enterprise_readiness.down.sql"

required_tables=(
  webhook_subscriptions
  webhook_deliveries
  connector_runs
  connector_errors
  dashboard_snapshots
  api_credentials
  task_templates
  security_audit_exports
)

for table in "${required_tables[@]}"; do
  rg -q "CREATE TABLE IF NOT EXISTS ${table}" "$UP_SQL"
  rg -q "DROP TABLE IF EXISTS ${table}" "$DOWN_SQL"
done

# Stage spec required indexes.
rg -q "idx_webhook_subscriptions_org_active" "$UP_SQL"
rg -q "idx_webhook_deliveries_org_created_at" "$UP_SQL"
rg -q "idx_connector_runs_org_created_at" "$UP_SQL"

# Contract safety: slice must not redefine canonical permit status enum.
if rg -q "permit_status" "$UP_SQL"; then
  echo "Unexpected contract change: permit_status enum touched in migration"
  exit 1
fi

echo "Stage 0.5 Slice 1 migration contract checks passed."
