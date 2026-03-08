-- Stage 3 Slice 1 foundations
-- Adds predictive intelligence and payout-orchestration persistence primitives.

BEGIN;

CREATE TABLE IF NOT EXISTS ahj_behavior_features (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  ahj_id TEXT NOT NULL,
  permit_type TEXT NOT NULL,
  feature_payload JSONB NOT NULL,
  source_window_start TIMESTAMPTZ,
  source_window_end TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ahj_behavior_features_ahj_permit_updated
  ON ahj_behavior_features (ahj_id, permit_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS preflight_risk_scores (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  permit_id UUID,
  ahj_id TEXT NOT NULL,
  permit_type TEXT NOT NULL,
  score NUMERIC(5,4) NOT NULL CHECK (score >= 0 AND score <= 1),
  band TEXT NOT NULL CHECK (band IN ('low', 'medium', 'high', 'critical')),
  confidence_score NUMERIC(5,4) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
  model_version TEXT NOT NULL,
  calibration_version TEXT,
  feature_snapshot_ref TEXT NOT NULL,
  top_risk_factors JSONB NOT NULL DEFAULT '[]'::JSONB,
  scored_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preflight_scores_org_project_scored
  ON preflight_risk_scores (organization_id, project_id, scored_at DESC);

CREATE TABLE IF NOT EXISTS recommendation_runs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  permit_id UUID,
  risk_score_id UUID NOT NULL REFERENCES preflight_risk_scores(id),
  recommendation_json JSONB NOT NULL,
  evidence_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  generated_by_model_version TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_org_project_generated
  ON recommendation_runs (organization_id, project_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS milestones (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  permit_id UUID NOT NULL,
  milestone_code TEXT NOT NULL,
  milestone_state TEXT NOT NULL,
  due_at TIMESTAMPTZ,
  verified_at TIMESTAMPTZ,
  verification_source TEXT,
  evidence_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_by UUID,
  updated_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_milestones_org_state_due
  ON milestones (organization_id, milestone_state, due_at);

CREATE TABLE IF NOT EXISTS payout_instructions (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  milestone_id UUID NOT NULL REFERENCES milestones(id),
  permit_id UUID NOT NULL,
  project_id UUID NOT NULL,
  beneficiary_id UUID NOT NULL,
  amount NUMERIC(18,2) NOT NULL CHECK (amount > 0),
  currency CHAR(3) NOT NULL,
  provider TEXT NOT NULL,
  provider_reference TEXT,
  instruction_state TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  failure_code TEXT,
  failure_reason TEXT,
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_payout_instructions_org_state_created
  ON payout_instructions (organization_id, instruction_state, created_at DESC);

CREATE TABLE IF NOT EXISTS financial_events (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  instruction_id UUID REFERENCES payout_instructions(id),
  milestone_id UUID REFERENCES milestones(id),
  event_type TEXT NOT NULL,
  amount NUMERIC(18,2) NOT NULL DEFAULT 0,
  currency CHAR(3),
  debit_account TEXT,
  credit_account TEXT,
  external_ref TEXT,
  trace_id TEXT,
  source_service TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  occurred_at TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_financial_events_org_event_occurred
  ON financial_events (organization_id, event_type, occurred_at DESC);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  provider TEXT NOT NULL,
  run_started_at TIMESTAMPTZ NOT NULL,
  run_finished_at TIMESTAMPTZ,
  run_status TEXT NOT NULL,
  settlement_reference TEXT,
  settlement_checksum TEXT,
  matched_count INTEGER NOT NULL DEFAULT 0,
  mismatched_count INTEGER NOT NULL DEFAULT 0,
  missing_internal_count INTEGER NOT NULL DEFAULT 0,
  missing_provider_count INTEGER NOT NULL DEFAULT 0,
  result_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_org_started
  ON reconciliation_runs (organization_id, run_started_at DESC);

ALTER TABLE IF EXISTS permits
  ADD COLUMN IF NOT EXISTS risk_score NUMERIC(5,4),
  ADD COLUMN IF NOT EXISTS risk_band TEXT,
  ADD COLUMN IF NOT EXISTS last_recommendation_at TIMESTAMPTZ;

COMMIT;
