-- Slice 3 contract tests: retry scheduling, DLQ handoff, and replay job queueing.

DO $$
DECLARE
  user_id uuid;
  org_id uuid;
  subscription_id uuid;
  delivery_retryable_id uuid;
  delivery_non_retryable_id uuid;
  out_delivery_id uuid;
  out_status text;
  out_next_retry_at timestamptz;
  out_dead_letter_id uuid;
  dl_id_for_replay uuid;
  replay_job_id uuid;
  replay_status_value text;
  replay_job_status_value text;
BEGIN
  INSERT INTO users(email, full_name)
  VALUES ('slice3_owner@example.com', 'Slice 3 Owner')
  RETURNING id INTO user_id;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice 3 Org', 'slice-3-org', user_id)
  RETURNING id INTO org_id;

  SELECT register_webhook_subscription(
    org_id,
    'https://hooks.example.com/slice3',
    ARRAY['permit.status_changed'],
    'enc_secret_slice3',
    user_id
  ) INTO subscription_id;

  INSERT INTO webhook_deliveries (
    organization_id,
    subscription_id,
    event_id,
    event_name,
    attempt,
    status,
    payload
  ) VALUES (
    org_id,
    subscription_id,
    gen_random_uuid(),
    'permit.status_changed',
    1,
    'pending',
    '{"permit_id":"retryable-1"}'::jsonb
  ) RETURNING id INTO delivery_retryable_id;

  SELECT delivery_id, status, next_retry_at, dead_letter_id
  INTO out_delivery_id, out_status, out_next_retry_at, out_dead_letter_id
  FROM enqueue_webhook_retry(delivery_retryable_id, 'upstream_timeout', 'timeout 1', 503);

  IF out_delivery_id IS DISTINCT FROM delivery_retryable_id THEN
    RAISE EXCEPTION 'retryable result delivery id mismatch';
  END IF;

  IF out_status <> 'retrying' THEN
    RAISE EXCEPTION 'expected retrying status for retryable failure, got %', out_status;
  END IF;

  IF out_next_retry_at IS NULL THEN
    RAISE EXCEPTION 'expected next_retry_at for retryable failure';
  END IF;

  IF out_dead_letter_id IS NOT NULL THEN
    RAISE EXCEPTION 'expected no dead letter id on first retryable failure';
  END IF;

  UPDATE webhook_deliveries
  SET retry_count = max_attempts - 1, status = 'retrying', next_retry_at = now()
  WHERE id = delivery_retryable_id;

  SELECT delivery_id, status, next_retry_at, dead_letter_id
  INTO out_delivery_id, out_status, out_next_retry_at, out_dead_letter_id
  FROM enqueue_webhook_retry(delivery_retryable_id, 'upstream_timeout', 'timeout maxed', 503);

  IF out_status <> 'dead_lettered' THEN
    RAISE EXCEPTION 'expected dead_lettered status when max attempts reached, got %', out_status;
  END IF;

  IF out_dead_letter_id IS NULL THEN
    RAISE EXCEPTION 'expected dead letter id when max attempts reached';
  END IF;

  -- Non-retryable failure should dead-letter immediately.
  INSERT INTO webhook_deliveries (
    organization_id,
    subscription_id,
    event_id,
    event_name,
    attempt,
    status,
    payload
  ) VALUES (
    org_id,
    subscription_id,
    gen_random_uuid(),
    'permit.status_changed',
    1,
    'pending',
    '{"permit_id":"non-retryable-1"}'::jsonb
  ) RETURNING id INTO delivery_non_retryable_id;

  SELECT delivery_id, status, next_retry_at, dead_letter_id
  INTO out_delivery_id, out_status, out_next_retry_at, out_dead_letter_id
  FROM enqueue_webhook_retry(delivery_non_retryable_id, 'bad_request', 'invalid payload', 400);

  IF out_status <> 'dead_lettered' THEN
    RAISE EXCEPTION 'expected dead_lettered status for non-retryable failure, got %', out_status;
  END IF;

  IF out_dead_letter_id IS NULL THEN
    RAISE EXCEPTION 'expected dead letter id for non-retryable failure';
  END IF;

  dl_id_for_replay := out_dead_letter_id;

  SELECT request_webhook_replay_for_dead_letter(dl_id_for_replay, user_id, 'manual replay after endpoint fix')
  INTO replay_job_id;

  IF replay_job_id IS NULL THEN
    RAISE EXCEPTION 'expected replay job id';
  END IF;

  SELECT wd.replay_status
  INTO replay_status_value
  FROM webhook_dead_letters wd
  WHERE id = dl_id_for_replay;

  IF replay_status_value <> 'queued' THEN
    RAISE EXCEPTION 'expected replay status queued, got %', replay_status_value;
  END IF;

  SELECT wrj.status
  INTO replay_job_status_value
  FROM webhook_replay_jobs wrj
  WHERE id = replay_job_id;

  IF replay_job_status_value <> 'queued' THEN
    RAISE EXCEPTION 'expected replay job status queued, got %', replay_job_status_value;
  END IF;
END $$;

-- Ensure there are dead letters recorded and replay queue rows available.
SELECT
  (SELECT count(*) FROM webhook_dead_letters) >= 2 AS has_dead_letters,
  (SELECT count(*) FROM webhook_replay_jobs) >= 1 AS has_replay_jobs;
