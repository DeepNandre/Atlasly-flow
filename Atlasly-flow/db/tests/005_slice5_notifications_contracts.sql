-- Slice 5 contract test: notification job dedupe, retry index, and tenant scope.

DO $$
DECLARE
  u1 uuid;
  u2 uuid;
  org1 uuid;
  org2 uuid;
  job1 uuid;
BEGIN
  INSERT INTO users(email, full_name) VALUES ('slice5-owner1@example.com', 'Slice5 Owner 1') RETURNING id INTO u1;
  INSERT INTO users(email, full_name) VALUES ('slice5-owner2@example.com', 'Slice5 Owner 2') RETURNING id INTO u2;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice5 Org One', 'slice5-org-one', u1)
  RETURNING id INTO org1;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice5 Org Two', 'slice5-org-two', u2)
  RETURNING id INTO org2;

  INSERT INTO notification_jobs(
    organization_id,
    user_id,
    channel,
    template_key,
    dedupe_key,
    payload
  ) VALUES (
    org1,
    u1,
    'email',
    'task_assigned',
    'task:123:assigned:v1',
    '{"task_id":"123"}'::jsonb
  )
  RETURNING id INTO job1;

  -- Duplicate dedupe key in same org + channel must fail.
  BEGIN
    INSERT INTO notification_jobs(
      organization_id,
      user_id,
      channel,
      template_key,
      dedupe_key,
      payload
    ) VALUES (
      org1,
      u1,
      'email',
      'task_assigned',
      'task:123:assigned:v1',
      '{"task_id":"123"}'::jsonb
    );
    RAISE EXCEPTION 'expected duplicate notification dedupe key to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Same dedupe key in same org but different channel is allowed.
  INSERT INTO notification_jobs(
    organization_id,
    user_id,
    channel,
    template_key,
    dedupe_key,
    payload
  ) VALUES (
    org1,
    u1,
    'in_app',
    'task_assigned',
    'task:123:assigned:v1',
    '{"task_id":"123"}'::jsonb
  );

  -- Same dedupe key+channel in different org is allowed.
  INSERT INTO notification_jobs(
    organization_id,
    user_id,
    channel,
    template_key,
    dedupe_key,
    payload
  ) VALUES (
    org2,
    u2,
    'email',
    'task_assigned',
    'task:123:assigned:v1',
    '{"task_id":"123"}'::jsonb
  );

  -- Negative attempt count must fail.
  BEGIN
    UPDATE notification_jobs
    SET attempt_count = -1
    WHERE id = job1;
    RAISE EXCEPTION 'expected attempt_count check to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  UPDATE notification_jobs
  SET status = 'retry',
      attempt_count = 1,
      next_attempt_at = now() + interval '5 minutes',
      last_error = 'smtp timeout'
  WHERE id = job1;
END $$;

DO $$
DECLARE
  n notification_jobs%ROWTYPE;
BEGIN
  SELECT *
  INTO n
  FROM notification_jobs
  WHERE organization_id = (
    SELECT id
    FROM organizations
    WHERE slug = 'slice5-org-one'
  )
    AND channel = 'email'
    AND dedupe_key = 'task:123:assigned:v1'
  LIMIT 1;

  IF n.status <> 'retry' THEN
    RAISE EXCEPTION 'expected status retry, got %', n.status;
  END IF;

  IF n.attempt_count <> 1 THEN
    RAISE EXCEPTION 'expected attempt_count 1, got %', n.attempt_count;
  END IF;

  IF n.next_attempt_at <= n.created_at THEN
    RAISE EXCEPTION 'expected next_attempt_at > created_at';
  END IF;
END $$;

SELECT
  EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'notification_jobs_status_next_attempt_idx'
  ) AS has_notification_retry_index,
  EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'notification_jobs_org_dedupe_channel_unique'
  ) AS has_notification_dedupe_constraint;
