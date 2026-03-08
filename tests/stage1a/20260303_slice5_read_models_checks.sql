-- Stage 1A Slice 5 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice5_read_models_checks.sql

DO $$
DECLARE
  v_letter_id uuid;
  v_snapshot_id uuid;
  v_status jsonb;
  v_extractions jsonb;
  v_snapshot jsonb;
  v_first_comment_id text;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_get_comment_letter_status'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_get_comment_letter_status function missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_list_comment_extractions'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_list_comment_extractions function missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_proc WHERE proname = 'stage1a_get_approval_snapshot'
  ) THEN
    RAISE EXCEPTION 'FAIL: stage1a_get_approval_snapshot function missing';
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
    'review_queueing',
    'slice5-test.pdf',
    'slice5-test-key'
  ) RETURNING id INTO v_letter_id;

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
    'cmt_2_111111111111',
    v_letter_id,
    'Second page extraction text long enough for constraints and list ordering.',
    'structural',
    'major',
    'Submit updated structural calculations signed by engineer.',
    'IBC 1604.4',
    2,
    'updated structural calculations',
    7,
    38,
    0.90,
    0.91,
    0.89,
    0.90,
    0.85,
    0.92,
    0.900,
    'needs_review'
  ),
  (
    'cmt_1_000000000000',
    v_letter_id,
    'First page extraction text long enough for constraints and ordering checks.',
    'electrical',
    'minor',
    'Revise panel schedule to reflect branch-circuit labeling updates.',
    'NEC 408.4',
    1,
    'panel schedule to reflect',
    11,
    36,
    0.94,
    0.92,
    0.90,
    0.95,
    0.88,
    0.93,
    0.930,
    'auto_accepted'
  );

  v_status := stage1a_get_comment_letter_status(v_letter_id);

  IF (v_status->>'extraction_count')::int <> 2 THEN
    RAISE EXCEPTION 'FAIL: extraction_count expected 2 got %', v_status->>'extraction_count';
  END IF;

  IF (v_status->>'requires_review_count')::int <> 1 THEN
    RAISE EXCEPTION 'FAIL: requires_review_count expected 1 got %', v_status->>'requires_review_count';
  END IF;

  IF (v_status->>'avg_confidence')::numeric <> 0.915 THEN
    RAISE EXCEPTION 'FAIL: avg_confidence expected 0.915 got %', v_status->>'avg_confidence';
  END IF;

  v_extractions := stage1a_list_comment_extractions(v_letter_id);

  IF jsonb_array_length(v_extractions->'extractions') <> 2 THEN
    RAISE EXCEPTION 'FAIL: expected 2 extraction rows in list';
  END IF;

  v_first_comment_id := (v_extractions->'extractions'->0->>'comment_id');
  IF v_first_comment_id <> 'cmt_1_000000000000' THEN
    RAISE EXCEPTION 'FAIL: extraction ordering mismatch, first comment id was %', v_first_comment_id;
  END IF;

  -- Approve and verify immutable snapshot retrieval.
  UPDATE comment_extractions
  SET status = 'reviewed_corrected'
  WHERE letter_id = v_letter_id
    AND status = 'needs_review';

  v_snapshot_id := stage1a_approve_comment_letter(v_letter_id, gen_random_uuid());

  v_snapshot := stage1a_get_approval_snapshot(v_letter_id);

  IF (v_snapshot->>'snapshot_id')::uuid <> v_snapshot_id THEN
    RAISE EXCEPTION 'FAIL: snapshot id mismatch';
  END IF;

  IF (v_snapshot->>'extraction_count')::int <> 2 THEN
    RAISE EXCEPTION 'FAIL: snapshot extraction_count expected 2 got %', v_snapshot->>'extraction_count';
  END IF;

  DELETE FROM comment_letter_event_emissions WHERE letter_id = v_letter_id;
  DELETE FROM comment_letter_approval_snapshots WHERE letter_id = v_letter_id;
  DELETE FROM comment_extractions WHERE letter_id = v_letter_id;
  DELETE FROM comment_letters WHERE id = v_letter_id;
END
$$;

SELECT 'PASS: Stage 1A Slice 5 read model checks completed' AS result;
