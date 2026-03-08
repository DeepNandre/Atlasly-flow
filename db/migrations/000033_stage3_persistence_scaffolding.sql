-- Stage 3 Slice 5 persistence scaffolding
-- Adds durable outbox + reconciliation invariants and replay-friendly constraints.

BEGIN;

CREATE TABLE IF NOT EXISTS stage3_event_outbox (
  event_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  event_version INTEGER NOT NULL DEFAULT 1,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  payload JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  produced_by TEXT NOT NULL,
  publish_state TEXT NOT NULL DEFAULT 'pending',
  publish_attempts INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, idempotency_key, event_type)
);

CREATE INDEX IF NOT EXISTS idx_stage3_outbox_publish_state_created
  ON stage3_event_outbox (publish_state, created_at);

ALTER TABLE IF EXISTS payout_instructions
  ADD CONSTRAINT chk_payout_instruction_state
  CHECK (instruction_state IN ('created','submitted','failed_transient','failed_terminal','settled','reversed'));

ALTER TABLE IF EXISTS reconciliation_runs
  ADD CONSTRAINT chk_reconciliation_run_status
  CHECK (run_status IN ('matched','mismatched','failed'));

CREATE UNIQUE INDEX IF NOT EXISTS ux_reconciliation_runs_org_provider_started
  ON reconciliation_runs (organization_id, provider, run_started_at);

CREATE INDEX IF NOT EXISTS idx_financial_events_org_instruction_occurred
  ON financial_events (organization_id, instruction_id, occurred_at DESC);

COMMIT;
