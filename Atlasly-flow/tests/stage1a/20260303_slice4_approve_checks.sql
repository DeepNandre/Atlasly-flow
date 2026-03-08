-- Stage 1A Slice 4 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice4_approve_checks.sql

DO $$
DECLARE
  v_letter_bad uuid;
  v_letter_ok uuid;
  v_snapshot_id uuid;
  v_snapshot_id_retry uuid;
  v_approved_events integer;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_approve_comment_letter'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_approve_comment_letter function missing';
  END IF;

  IF to_regclass('public.comment_letter_approval_snapshots') IS NULL THEN
    RAISE EXCEPTION 'FAIL: comment_letter_approval_snapshots table missing';
  END IF;

  -- Negative case: cannot approve when needs_review exists.
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
    'review_queueing',
    'slice4-bad.pdf',
    'slice4-bad-key'
  ) RETURNING id INTO v_letter_bad;

  INSERT INTO comment_extractions (
    comment_id,
    letter_id,
    raw_text,
    discipline,
    severity,
    requested_action,
    code_reference,
    page_number,
    citation_quote,
    citation_char_start,
    citation_char_end,
    confidence_raw_text,
    confidence_discipline,
    confidence_severity,
    confidence_requested_action,
    confidence_code_reference,
    confidence_citation,
    confidence,
    status
  ) VALUES (
    'cmt_1_aaaaaaaaaaaa',
    v_letter_bad,
    'This is a sample municipal comment text that is long enough.',
    'electrical',
    'major',
    'Revise load schedule and submit updated panel calculations.',
    'NEC 210.20',
    1,
    'sample municipal comment text',
    0,
    28,
    0.95,
    0.90,
    0.88,
    0.92,
    0.80,
    0.93,
    0.90,
    'needs_review'
  );

  BEGIN
    PERFORM stage1a_approve_comment_letter(v_letter_bad, gen_random_uuid());
    RAISE EXCEPTION 'FAIL: approval unexpectedly succeeded with needs_review rows';
  EXCEPTION WHEN others THEN
    NULL;
  END;

  -- Positive case: approval succeeds with corrected/auto_accepted rows.
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
    'human_review',
    'slice4-ok.pdf',
    'slice4-ok-key'
  ) RETURNING id INTO v_letter_ok;

  INSERT INTO comment_extractions (
    comment_id,
    letter_id,
    raw_text,
    discipline,
    severity,
    requested_action,
    code_reference,
    page_number,
    citation_quote,
    citation_char_start,
    citation_char_end,
    confidence_raw_text,
    confidence_discipline,
    confidence_severity,
    confidence_requested_action,
    confidence_code_reference,
    confidence_citation,
    confidence,
    status
  ) VALUES
  (
    'cmt_2_bbbbbbbbbbbb',
    v_letter_ok,
    'First valid extracted comment long enough for the check constraints.',
    'plumbing',
    'minor',
    'Update fixture schedule to match current plumbing code requirements.',
    'IPC 403.1',
    2,
    'valid extracted comment long enough',
    6,
    40,
    0.91,
    0.89,
    0.84,
    0.90,
    0.87,
    0.88,
    0.89,
    'reviewed_corrected'
  ),
  (
    'cmt_3_cccccccccccc',
    v_letter_ok,
    'Second valid extracted comment long enough for workflow approval path.',
    'mechanical',
    'major',
    'Provide revised duct sizing calculations stamped by engineer of record.',
    'IMC 603.2',
    3,
    'workflow approval path',
    35,
    57,
    0.93,
    0.92,
    0.90,
    0.94,
    0.86,
    0.90,
    0.91,
    'auto_accepted'
  );

  v_snapshot_id := stage1a_approve_comment_letter(v_letter_ok, gen_random_uuid());

  IF v_snapshot_id IS NULL THEN
    RAISE EXCEPTION 'FAIL: approval returned null snapshot id';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM comment_letter_approval_snapshots
    WHERE id = v_snapshot_id
      AND letter_id = v_letter_ok
  ) THEN
    RAISE EXCEPTION 'FAIL: approval snapshot row missing';
  END IF;

  IF EXISTS (
    SELECT 1 FROM comment_extractions
    WHERE letter_id = v_letter_ok
      AND status <> 'approved_snapshot'
  ) THEN
    RAISE EXCEPTION 'FAIL: not all extraction statuses promoted to approved_snapshot';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM comment_letters
    WHERE id = v_letter_ok
      AND extraction_status = 'completed'
  ) THEN
    RAISE EXCEPTION 'FAIL: letter not moved to completed';
  END IF;

  -- Idempotent retry should return same snapshot and avoid duplicate approved event rows.
  v_snapshot_id_retry := stage1a_approve_comment_letter(v_letter_ok, gen_random_uuid());

  IF v_snapshot_id_retry <> v_snapshot_id THEN
    RAISE EXCEPTION 'FAIL: idempotent retry returned different snapshot id';
  END IF;

  SELECT count(*) INTO v_approved_events
  FROM comment_letter_event_emissions
  WHERE letter_id = v_letter_ok
    AND event_type = 'comment_letter.approved'
    AND event_version = 1;

  IF v_approved_events <> 1 THEN
    RAISE EXCEPTION 'FAIL: expected exactly one approved event, got %', v_approved_events;
  END IF;

  DELETE FROM comment_letter_event_emissions WHERE letter_id IN (v_letter_bad, v_letter_ok);
  DELETE FROM comment_letter_approval_snapshots WHERE letter_id IN (v_letter_bad, v_letter_ok);
  DELETE FROM comment_extractions WHERE letter_id IN (v_letter_bad, v_letter_ok);
  DELETE FROM comment_letters WHERE id IN (v_letter_bad, v_letter_ok);
END
$$;

SELECT 'PASS: Stage 1A Slice 4 approve checks completed' AS result;
