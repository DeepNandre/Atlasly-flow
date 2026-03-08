-- Rollback for Stage 3 Slice 1 foundations

BEGIN;

ALTER TABLE IF EXISTS permits
  DROP COLUMN IF EXISTS last_recommendation_at,
  DROP COLUMN IF EXISTS risk_band,
  DROP COLUMN IF EXISTS risk_score;

DROP TABLE IF EXISTS reconciliation_runs;
DROP TABLE IF EXISTS financial_events;
DROP TABLE IF EXISTS payout_instructions;
DROP TABLE IF EXISTS milestones;
DROP TABLE IF EXISTS recommendation_runs;
DROP TABLE IF EXISTS preflight_risk_scores;
DROP TABLE IF EXISTS ahj_behavior_features;

COMMIT;
