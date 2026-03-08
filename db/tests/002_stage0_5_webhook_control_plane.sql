-- Slice 2 contract tests: Stage 0.5 webhook control-plane registration and retrieval.

DO $$
DECLARE
  org_id uuid;
  sub_id uuid;
  duplicate_error text;
  insecure_url_error text;
  invalid_event_error text;
  listed_count integer;
BEGIN
  INSERT INTO users(email, full_name)
  VALUES ('slice2_owner@example.com', 'Slice 2 Owner')
  RETURNING id INTO org_id;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice 2 Org', 'slice-2-org', org_id)
  RETURNING id INTO org_id;

  SELECT register_webhook_subscription(
    org_id,
    'https://hooks.example.com/atlasly',
    ARRAY['permit.status_changed', 'task.created'],
    'enc_secret_v1',
    NULL
  ) INTO sub_id;

  IF sub_id IS NULL THEN
    RAISE EXCEPTION 'register_webhook_subscription must return an id';
  END IF;

  -- Duplicate active subscription for same org + target must fail.
  BEGIN
    PERFORM register_webhook_subscription(
      org_id,
      'https://hooks.example.com/atlasly',
      ARRAY['task.assigned'],
      'enc_secret_v2',
      NULL
    );
    RAISE EXCEPTION 'expected duplicate active subscription to fail';
  EXCEPTION WHEN unique_violation THEN
    duplicate_error := 'ok';
  END;

  IF duplicate_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'duplicate subscription check did not fire';
  END IF;

  -- Non-https url must fail.
  BEGIN
    PERFORM register_webhook_subscription(
      org_id,
      'http://hooks.example.com/plaintext',
      ARRAY['task.created'],
      'enc_secret_v3',
      NULL
    );
    RAISE EXCEPTION 'expected insecure url registration to fail';
  EXCEPTION WHEN check_violation THEN
    insecure_url_error := 'ok';
  END;

  IF insecure_url_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'https constraint check did not fire';
  END IF;

  -- Unknown event type must fail.
  BEGIN
    PERFORM register_webhook_subscription(
      org_id,
      'https://hooks.example.com/unknown-event',
      ARRAY['permit.rejected'],
      'enc_secret_v4',
      NULL
    );
    RAISE EXCEPTION 'expected unknown event registration to fail';
  EXCEPTION WHEN check_violation THEN
    invalid_event_error := 'ok';
  END;

  IF invalid_event_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'allowed webhook event check did not fire';
  END IF;

  INSERT INTO webhook_deliveries (
    organization_id,
    subscription_id,
    event_id,
    event_name,
    attempt,
    status,
    payload,
    response_code,
    error_code
  ) VALUES
    (
      org_id,
      sub_id,
      gen_random_uuid(),
      'task.created',
      1,
      'delivered',
      '{"task_id":"t-1"}'::jsonb,
      200,
      NULL
    ),
    (
      org_id,
      sub_id,
      gen_random_uuid(),
      'permit.status_changed',
      1,
      'failed_retryable',
      '{"permit_id":"p-1"}'::jsonb,
      503,
      'upstream_timeout'
    );

  SELECT count(*)
  INTO listed_count
  FROM list_webhook_events(org_id, sub_id, NULL, NULL, NULL, 50, 0);

  IF listed_count <> 2 THEN
    RAISE EXCEPTION 'list_webhook_events expected 2 rows, got %', listed_count;
  END IF;
END $$;

-- Ensure stage contract enums remain intact (no accidental contract mutation).
SELECT
  EXISTS (
    SELECT 1
    FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'submitted'
  ) AS has_permit_status_submitted,
  EXISTS (
    SELECT 1
    FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'issued'
  ) AS has_permit_status_issued;
