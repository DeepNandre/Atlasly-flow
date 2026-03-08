-- Stage 1A Slice 6 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice6_pipeline_entrypoint_checks.sql

DO $$
DECLARE
  v_org uuid := gen_random_uuid();
  v_project uuid := gen_random_uuid();
  v_document uuid := gen_random_uuid();
  v_user uuid := gen_random_uuid();
  v_letter_id uuid;
  v_letter_id_retry uuid;
  v_parsing_started_count integer;
  v_extraction_completed_count integer;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_create_comment_letter'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_create_comment_letter function missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_finalize_extraction'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_finalize_extraction function missing';
  END IF;

  v_letter_id := stage1a_create_comment_letter(
    v_org,
    v_project,
    v_document,
    v_user,
    'slice6-idem-key',
    'slice6.pdf'
  );

  v_letter_id_retry := stage1a_create_comment_letter(
    v_org,
    v_project,
    v_document,
    v_user,
    'slice6-idem-key',
    'slice6.pdf'
  );

  IF v_letter_id <> v_letter_id_retry THEN
    RAISE EXCEPTION 'FAIL: create idempotency returned different letter IDs';
  END IF;

  SELECT count(*) INTO v_parsing_started_count
  FROM comment_letter_event_emissions
  WHERE letter_id = v_letter_id
    AND event_type = 'comment_letter.parsing_started'
    AND event_version = 1;

  IF v_parsing_started_count <> 1 THEN
    RAISE EXCEPTION 'FAIL: expected one parsing_started event, got %', v_parsing_started_count;
  END IF;

  -- Advance through valid state transitions to normalizing_validating.
  UPDATE comment_letters SET extraction_status = 'ocr_precheck' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'extracting_comments' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'normalizing_validating' WHERE id = v_letter_id;

  PERFORM stage1a_finalize_extraction(
    v_letter_id,
    v_document,
    2,
    0.912,
    1
  );

  IF NOT EXISTS (
    SELECT 1 FROM comment_letters
    WHERE id = v_letter_id
      AND extraction_status = 'review_queueing'
  ) THEN
    RAISE EXCEPTION 'FAIL: finalize did not move letter to review_queueing';
  END IF;

  PERFORM stage1a_finalize_extraction(
    v_letter_id,
    v_document,
    2,
    0.912,
    1
  );

  SELECT count(*) INTO v_extraction_completed_count
  FROM comment_letter_event_emissions
  WHERE letter_id = v_letter_id
    AND event_type = 'comment_letter.extraction_completed'
    AND event_version = 1;

  IF v_extraction_completed_count <> 1 THEN
    RAISE EXCEPTION 'FAIL: expected exactly one extraction_completed event, got %', v_extraction_completed_count;
  END IF;

  DELETE FROM comment_letter_event_emissions WHERE letter_id = v_letter_id;
  DELETE FROM comment_letters WHERE id = v_letter_id;
END
$$;

SELECT 'PASS: Stage 1A Slice 6 pipeline entrypoint checks completed' AS result;
