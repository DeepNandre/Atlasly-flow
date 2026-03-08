-- Slice 4 contract tests: connector run lifecycle and error taxonomy enforcement.

DO $$
DECLARE
  user_id uuid;
  org_id uuid;
  run_id uuid;
  error_id uuid;
  invalid_classification_error text;
  terminal_twice_error text;
  run_status_value text;
  duration_ms_value integer;
  retryable_value boolean;
BEGIN
  INSERT INTO users(email, full_name)
  VALUES ('slice4_owner@example.com', 'Slice 4 Owner')
  RETURNING id INTO user_id;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice 4 Org', 'slice-4-org', user_id)
  RETURNING id INTO org_id;

  SELECT start_connector_run(
    org_id,
    'opengov',
    'manual',
    'delta',
    '{"cursor":"abc"}'::jsonb
  ) INTO run_id;

  IF run_id IS NULL THEN
    RAISE EXCEPTION 'expected run id from start_connector_run';
  END IF;

  SELECT record_connector_error(
    run_id,
    'rate_limit.exceeded',
    '429 from upstream',
    '429',
    '{"attempt":1}'::jsonb,
    'ext-1',
    NULL
  ) INTO error_id;

  IF error_id IS NULL THEN
    RAISE EXCEPTION 'expected connector error id';
  END IF;

  SELECT ce.is_retryable
  INTO retryable_value
  FROM connector_errors ce
  WHERE ce.id = error_id;

  IF retryable_value IS DISTINCT FROM TRUE THEN
    RAISE EXCEPTION 'expected rate_limit.exceeded to default retryable=true';
  END IF;

  -- Invalid error classification must fail.
  BEGIN
    PERFORM record_connector_error(
      run_id,
      'auth.bad_value',
      'invalid classification',
      NULL,
      NULL,
      NULL,
      NULL
    );
    RAISE EXCEPTION 'expected invalid classification to fail';
  EXCEPTION WHEN check_violation THEN
    invalid_classification_error := 'ok';
  END;

  IF invalid_classification_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'connector classification check did not fire';
  END IF;

  PERFORM complete_connector_run(
    run_id,
    'partial',
    25,
    20,
    5,
    '{"cursor":"def"}'::jsonb,
    '{"reason":"partial failures"}'::jsonb
  );

  SELECT cr.run_status, cr.duration_ms
  INTO run_status_value, duration_ms_value
  FROM connector_runs cr
  WHERE cr.id = run_id;

  IF run_status_value <> 'partial' THEN
    RAISE EXCEPTION 'expected run status partial, got %', run_status_value;
  END IF;

  IF duration_ms_value IS NULL OR duration_ms_value < 0 THEN
    RAISE EXCEPTION 'expected non-negative duration_ms';
  END IF;

  -- Completing a terminal run again must fail.
  BEGIN
    PERFORM complete_connector_run(
      run_id,
      'succeeded',
      25,
      25,
      0,
      '{"cursor":"xyz"}'::jsonb,
      NULL
    );
    RAISE EXCEPTION 'expected second completion to fail';
  EXCEPTION WHEN raise_exception THEN
    terminal_twice_error := 'ok';
  END;

  IF terminal_twice_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'expected terminal second completion to fail';
  END IF;
END $$;

-- Ensure shared permit_status contract still exists and includes canonical values.
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
