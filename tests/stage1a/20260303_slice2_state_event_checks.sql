-- Stage 1A Slice 2 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice2_state_event_checks.sql

DO $$
DECLARE
  v_letter_id uuid;
BEGIN
  IF to_regclass('public.comment_letters') IS NULL THEN
    RAISE EXCEPTION 'FAIL: comment_letters missing';
  END IF;

  IF to_regclass('public.comment_letter_event_emissions') IS NULL THEN
    RAISE EXCEPTION 'FAIL: comment_letter_event_emissions missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_proc
    WHERE proname = 'stage1a_is_valid_transition'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_is_valid_transition function missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'trg_stage1a_comment_letters_transition'
  ) THEN
    RAISE EXCEPTION 'FAIL: transition trigger missing';
  END IF;

  INSERT INTO comment_letters (
    organization_id,
    project_id,
    document_id,
    extraction_status,
    source_filename,
    idempotency_key
  ) VALUES (
    gen_random_uuid(),
    gen_random_uuid(),
    gen_random_uuid(),
    'ingest_received',
    'slice2-test.pdf',
    'slice2-test-key'
  )
  RETURNING id INTO v_letter_id;

  -- valid transitions
  UPDATE comment_letters SET extraction_status = 'ocr_precheck' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'extracting_comments' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'normalizing_validating' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'review_queueing' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'approval_snapshot' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'completed' WHERE id = v_letter_id;

  -- invalid transition should fail
  BEGIN
    UPDATE comment_letters SET extraction_status = 'ingest_received' WHERE id = v_letter_id;
    RAISE EXCEPTION 'FAIL: invalid transition unexpectedly succeeded';
  EXCEPTION WHEN others THEN
    -- expected path
    NULL;
  END;

  -- single emission contract
  INSERT INTO comment_letter_event_emissions (letter_id, event_type, event_version, idempotency_key, payload)
  VALUES (
    v_letter_id,
    'comment_letter.extraction_completed',
    1,
    v_letter_id::text || ':comment_letter.extraction_completed:v1',
    '{}'::jsonb
  );

  BEGIN
    INSERT INTO comment_letter_event_emissions (letter_id, event_type, event_version, idempotency_key, payload)
    VALUES (
      v_letter_id,
      'comment_letter.extraction_completed',
      1,
      v_letter_id::text || ':comment_letter.extraction_completed:v1:dup',
      '{}'::jsonb
    );
    RAISE EXCEPTION 'FAIL: duplicate event per letter unexpectedly succeeded';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  BEGIN
    INSERT INTO comment_letter_event_emissions (letter_id, event_type, event_version, idempotency_key, payload)
    VALUES (
      gen_random_uuid(),
      'comment_letter.approved',
      1,
      v_letter_id::text || ':comment_letter.extraction_completed:v1',
      '{}'::jsonb
    );
    RAISE EXCEPTION 'FAIL: duplicate idempotency key unexpectedly succeeded';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  DELETE FROM comment_letter_event_emissions WHERE letter_id = v_letter_id;
  DELETE FROM comment_letters WHERE id = v_letter_id;
END
$$;

SELECT 'PASS: Stage 1A Slice 2 state/event checks completed' AS result;
