-- Slice 5 contract tests: dashboard snapshot and API credential lifecycle controls.

DO $$
DECLARE
  user_id uuid;
  org_id uuid;
  cred_id uuid;
  rotated_cred_id uuid;
  invalid_scope_error text;
  long_expiry_error text;
  latest_snapshot_id uuid;
  latest_snapshot_metric numeric;
BEGIN
  INSERT INTO users(email, full_name)
  VALUES ('slice5_owner@example.com', 'Slice 5 Owner')
  RETURNING id INTO user_id;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice 5 Org', 'slice-5-org', user_id)
  RETURNING id INTO org_id;

  SELECT create_api_credential(
    org_id,
    user_id,
    'primary key',
    'ak_live_001',
    repeat('a', 64),
    ARRAY['webhooks:read', 'dashboard:read'],
    now() + interval '30 days'
  ) INTO cred_id;

  IF cred_id IS NULL THEN
    RAISE EXCEPTION 'expected created credential id';
  END IF;

  -- Invalid scope should fail.
  BEGIN
    PERFORM create_api_credential(
      org_id,
      user_id,
      'invalid scope key',
      'ak_live_002',
      repeat('b', 64),
      ARRAY['dashboard:delete'],
      now() + interval '10 days'
    );
    RAISE EXCEPTION 'expected invalid scope to fail';
  EXCEPTION WHEN check_violation THEN
    invalid_scope_error := 'ok';
  END;

  IF invalid_scope_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'api scope check did not fire';
  END IF;

  -- Expiry > 365 days should fail.
  BEGIN
    PERFORM create_api_credential(
      org_id,
      user_id,
      'long expiry key',
      'ak_live_003',
      repeat('c', 64),
      ARRAY['dashboard:read'],
      now() + interval '366 days'
    );
    RAISE EXCEPTION 'expected long expiry to fail';
  EXCEPTION WHEN raise_exception THEN
    long_expiry_error := 'ok';
  END;

  IF long_expiry_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'expiry window guard did not fire';
  END IF;

  SELECT rotate_api_credential(
    cred_id,
    user_id,
    'rotated key',
    'ak_live_004',
    repeat('d', 64),
    ARRAY['webhooks:read', 'webhooks:write'],
    now() + interval '45 days'
  ) INTO rotated_cred_id;

  IF rotated_cred_id IS NULL THEN
    RAISE EXCEPTION 'expected rotated credential id';
  END IF;

  -- Old key should now be revoked and have rotated_at.
  PERFORM 1
  FROM api_credentials
  WHERE id = cred_id
    AND revoked_at IS NOT NULL
    AND rotated_at IS NOT NULL;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'expected old credential to be revoked + rotated';
  END IF;

  PERFORM revoke_api_credential(rotated_cred_id, user_id, 'manual revoke after incident');

  PERFORM 1
  FROM api_credentials
  WHERE id = rotated_cred_id
    AND revoked_at IS NOT NULL
    AND revoked_reason = 'manual revoke after incident';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'expected rotated credential revoke to persist reason';
  END IF;

  -- Dashboard snapshot upsert + latest lookup.
  PERFORM upsert_dashboard_snapshot(
    org_id,
    date_trunc('minute', now()),
    now() - interval '30 seconds',
    '{
      "permits_total": 100,
      "permit_cycle_time_p50_days": 12.3,
      "permit_cycle_time_p90_days": 30.1,
      "corrections_rate": 0.22,
      "approval_rate_30d": 0.71,
      "task_sla_breach_rate": 0.08,
      "connector_health_score": 88.5,
      "webhook_delivery_success_rate": 0.995
    }'::jsonb,
    false
  );

  -- Upsert same snapshot_at should update metrics.
  PERFORM upsert_dashboard_snapshot(
    org_id,
    date_trunc('minute', now()),
    now() - interval '20 seconds',
    '{
      "permits_total": 101,
      "permit_cycle_time_p50_days": 12.0,
      "permit_cycle_time_p90_days": 29.8,
      "corrections_rate": 0.21,
      "approval_rate_30d": 0.72,
      "task_sla_breach_rate": 0.07,
      "connector_health_score": 89.5,
      "webhook_delivery_success_rate": 0.996
    }'::jsonb,
    false
  );

  SELECT g.snapshot_id, (g.metrics->>'permits_total')::numeric
  INTO latest_snapshot_id, latest_snapshot_metric
  FROM get_latest_dashboard_snapshot(org_id) g;

  IF latest_snapshot_id IS NULL THEN
    RAISE EXCEPTION 'expected latest dashboard snapshot';
  END IF;

  IF latest_snapshot_metric <> 101 THEN
    RAISE EXCEPTION 'expected upserted permits_total=101, got %', latest_snapshot_metric;
  END IF;
END $$;

-- Contract guard: shared permit_status remains unchanged.
SELECT
  EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'submitted'
  ) AS has_permit_status_submitted,
  EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'issued'
  ) AS has_permit_status_issued;
