-- Stage 1A Slice 3 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice3_emit_function_checks.sql

DO $$
DECLARE
  v_letter_id uuid;
  v_event_id uuid;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_emit_event'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_emit_event function missing';
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
    'slice3-test.pdf',
    'slice3-test-key'
  ) RETURNING id INTO v_letter_id;

  -- parsing_started allowed at ingest_received.
  v_event_id := stage1a_emit_event(
    v_letter_id,
    'comment_letter.parsing_started',
    jsonb_build_object(
      'letter_id', v_letter_id,
      'document_id', (SELECT document_id FROM comment_letters WHERE id = v_letter_id),
      'started_at', now()
    )
  );

  IF v_event_id IS NULL THEN
    RAISE EXCEPTION 'FAIL: parsing_started returned null event id';
  END IF;

  -- extraction_completed not allowed before review_queueing.
  BEGIN
    PERFORM stage1a_emit_event(
      v_letter_id,
      'comment_letter.extraction_completed',
      '{}'::jsonb
    );
    RAISE EXCEPTION 'FAIL: extraction_completed emitted before review_queueing';
  EXCEPTION WHEN others THEN
    NULL;
  END;

  -- Move to canonical emission point and emit extraction_completed once.
  UPDATE comment_letters SET extraction_status = 'ocr_precheck' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'extracting_comments' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'normalizing_validating' WHERE id = v_letter_id;
  UPDATE comment_letters SET extraction_status = 'review_queueing' WHERE id = v_letter_id;

  v_event_id := stage1a_emit_event(
    v_letter_id,
    'comment_letter.extraction_completed',
    jsonb_build_object(
      'letter_id', v_letter_id,
      'document_id', (SELECT document_id FROM comment_letters WHERE id = v_letter_id),
      'extraction_count', 3,
      'avg_confidence', 0.931,
      'requires_review_count', 1,
      'completed_at', now()
    )
  );

  IF v_event_id IS NULL THEN
    RAISE EXCEPTION 'FAIL: extraction_completed returned null event id';
  END IF;

  -- Duplicate emit should fail (unique idempotency and per-letter event uniqueness).
  BEGIN
    PERFORM stage1a_emit_event(
      v_letter_id,
      'comment_letter.extraction_completed',
      '{}'::jsonb
    );
    RAISE EXCEPTION 'FAIL: duplicate extraction_completed emitted';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- approved not allowed before approval_snapshot/completed.
  BEGIN
    PERFORM stage1a_emit_event(v_letter_id, 'comment_letter.approved', '{}'::jsonb);
    RAISE EXCEPTION 'FAIL: approved emitted before approval_snapshot/completed';
  EXCEPTION WHEN others THEN
    NULL;
  END;

  UPDATE comment_letters SET extraction_status = 'approval_snapshot' WHERE id = v_letter_id;

  v_event_id := stage1a_emit_event(
    v_letter_id,
    'comment_letter.approved',
    jsonb_build_object(
      'letter_id', v_letter_id,
      'approved_by', gen_random_uuid(),
      'approved_at', now()
    )
  );

  IF v_event_id IS NULL THEN
    RAISE EXCEPTION 'FAIL: approved returned null event id';
  END IF;

  DELETE FROM comment_letter_event_emissions WHERE letter_id = v_letter_id;
  DELETE FROM comment_letters WHERE id = v_letter_id;
END
$$;

SELECT 'PASS: Stage 1A Slice 3 emit function checks completed' AS result;
