-- Stage 3 Slice 6 contract test:
-- validates outbox idempotency uniqueness, payout state check, and reconciliation constraints.

DO $$
DECLARE
  org_id uuid := gen_random_uuid();
  milestone_id uuid := gen_random_uuid();
  permit_id uuid := gen_random_uuid();
  project_id uuid := gen_random_uuid();
  started_at timestamptz := now();
BEGIN
  INSERT INTO milestones (
    id, organization_id, project_id, permit_id, milestone_code, milestone_state
  ) VALUES (
    milestone_id, org_id, project_id, permit_id, 'permit_issued', 'payout_eligible'
  );

  INSERT INTO payout_instructions (
    id,
    organization_id,
    milestone_id,
    permit_id,
    project_id,
    beneficiary_id,
    amount,
    currency,
    provider,
    instruction_state,
    idempotency_key
  ) VALUES (
    gen_random_uuid(),
    org_id,
    milestone_id,
    permit_id,
    project_id,
    gen_random_uuid(),
    1200.00,
    'USD',
    'provider_sandbox',
    'created',
    'idem-db-1'
  );

  BEGIN
    INSERT INTO payout_instructions (
      id,
      organization_id,
      milestone_id,
      permit_id,
      project_id,
      beneficiary_id,
      amount,
      currency,
      provider,
      instruction_state,
      idempotency_key
    ) VALUES (
      gen_random_uuid(),
      org_id,
      milestone_id,
      permit_id,
      project_id,
      gen_random_uuid(),
      10.00,
      'USD',
      'provider_sandbox',
      'pending',
      'idem-db-2'
    );
    RAISE EXCEPTION 'expected payout instruction state check constraint to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  INSERT INTO stage3_event_outbox (
    event_id,
    organization_id,
    event_type,
    event_version,
    aggregate_type,
    aggregate_id,
    idempotency_key,
    trace_id,
    payload,
    occurred_at,
    produced_by
  ) VALUES (
    gen_random_uuid(),
    org_id,
    'payout.instruction_created',
    1,
    'payout_instruction',
    milestone_id::text,
    'idem-outbox-1',
    'trc-db-1',
    '{"ok":true}'::jsonb,
    now(),
    'payout-service'
  );

  BEGIN
    INSERT INTO stage3_event_outbox (
      event_id,
      organization_id,
      event_type,
      event_version,
      aggregate_type,
      aggregate_id,
      idempotency_key,
      trace_id,
      payload,
      occurred_at,
      produced_by
    ) VALUES (
      gen_random_uuid(),
      org_id,
      'payout.instruction_created',
      1,
      'payout_instruction',
      milestone_id::text,
      'idem-outbox-1',
      'trc-db-2',
      '{"ok":true}'::jsonb,
      now(),
      'payout-service'
    );
    RAISE EXCEPTION 'expected stage3_event_outbox unique constraint to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  INSERT INTO reconciliation_runs (
    id,
    organization_id,
    provider,
    run_started_at,
    run_status,
    matched_count,
    mismatched_count,
    missing_internal_count,
    missing_provider_count,
    result_payload
  ) VALUES (
    gen_random_uuid(),
    org_id,
    'provider_sandbox',
    started_at,
    'matched',
    1,
    0,
    0,
    0,
    '{}'::jsonb
  );

  BEGIN
    INSERT INTO reconciliation_runs (
      id,
      organization_id,
      provider,
      run_started_at,
      run_status,
      matched_count,
      mismatched_count,
      missing_internal_count,
      missing_provider_count,
      result_payload
    ) VALUES (
      gen_random_uuid(),
      org_id,
      'provider_sandbox',
      now() + interval '1 minute',
      'invalid_status',
      0,
      1,
      0,
      1,
      '{}'::jsonb
    );
    RAISE EXCEPTION 'expected reconciliation run status check to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    INSERT INTO reconciliation_runs (
      id,
      organization_id,
      provider,
      run_started_at,
      run_status,
      matched_count,
      mismatched_count,
      missing_internal_count,
      missing_provider_count,
      result_payload
    ) VALUES (
      gen_random_uuid(),
      org_id,
      'provider_sandbox',
      started_at,
      'matched',
      1,
      0,
      0,
      0,
      '{}'::jsonb
    );
    RAISE EXCEPTION 'expected reconciliation run unique index to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END $$;

SELECT
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_stage3_outbox_publish_state_created'
  ) AS has_stage3_outbox_publish_idx,
  EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_payout_instruction_state'
  ) AS has_payout_state_check,
  EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_reconciliation_run_status'
  ) AS has_reconciliation_status_check,
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ux_reconciliation_runs_org_provider_started'
  ) AS has_reconciliation_unique_idx;
