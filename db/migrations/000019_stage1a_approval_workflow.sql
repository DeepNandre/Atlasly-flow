-- Stage 1A Slice 4 migration
-- Adds immutable approval snapshot and approval function for /comment-letters/{letterId}/approve.
-- No shared event/API contract name changes.

BEGIN;

CREATE TABLE IF NOT EXISTS comment_letter_approval_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  letter_id uuid NOT NULL REFERENCES comment_letters(id) ON DELETE CASCADE,
  approved_by uuid NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT now(),
  extraction_count integer NOT NULL CHECK (extraction_count >= 0),
  snapshot_payload jsonb NOT NULL,
  UNIQUE (letter_id)
);

CREATE INDEX IF NOT EXISTS idx_comment_letter_approval_snapshots_approved_at
  ON comment_letter_approval_snapshots(approved_at DESC);

CREATE OR REPLACE FUNCTION stage1a_approve_comment_letter(
  p_letter_id uuid,
  p_approved_by uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_snapshot_id uuid;
  v_needs_review_count integer;
  v_extraction_count integer;
  v_snapshot_payload jsonb;
  v_current_status text;
BEGIN
  SELECT extraction_status INTO v_current_status
  FROM comment_letters
  WHERE id = p_letter_id
  FOR UPDATE;

  IF v_current_status IS NULL THEN
    RAISE EXCEPTION 'Letter % not found', p_letter_id;
  END IF;

  -- Idempotent retry path after completion.
  IF v_current_status = 'completed' THEN
    SELECT id INTO v_snapshot_id
    FROM comment_letter_approval_snapshots
    WHERE letter_id = p_letter_id;

    IF v_snapshot_id IS NULL THEN
      RAISE EXCEPTION 'Letter % is completed but snapshot is missing', p_letter_id;
    END IF;

    RETURN v_snapshot_id;
  END IF;

  SELECT count(*) INTO v_needs_review_count
  FROM comment_extractions
  WHERE letter_id = p_letter_id
    AND status = 'needs_review';

  IF v_needs_review_count > 0 THEN
    RAISE EXCEPTION 'Cannot approve letter % with % needs_review extractions', p_letter_id, v_needs_review_count;
  END IF;

  SELECT count(*) INTO v_extraction_count
  FROM comment_extractions
  WHERE letter_id = p_letter_id;

  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'comment_id', comment_id,
        'raw_text', raw_text,
        'discipline', discipline,
        'severity', severity,
        'requested_action', requested_action,
        'code_reference', code_reference,
        'page_number', page_number,
        'confidence', confidence,
        'status', status,
        'created_at', created_at,
        'updated_at', updated_at
      )
      ORDER BY page_number, comment_id
    ),
    '[]'::jsonb
  ) INTO v_snapshot_payload
  FROM comment_extractions
  WHERE letter_id = p_letter_id;

  UPDATE comment_letters
  SET extraction_status = 'approval_snapshot',
      approved_at = now()
  WHERE id = p_letter_id
    AND extraction_status IN ('review_queueing', 'human_review', 'approval_snapshot');

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Letter % is not in an approvable status', p_letter_id;
  END IF;

  UPDATE comment_extractions
  SET status = 'approved_snapshot',
      updated_at = now()
  WHERE letter_id = p_letter_id
    AND status IN ('auto_accepted', 'reviewed_corrected');

  INSERT INTO comment_letter_approval_snapshots (
    letter_id,
    approved_by,
    approved_at,
    extraction_count,
    snapshot_payload
  ) VALUES (
    p_letter_id,
    p_approved_by,
    now(),
    v_extraction_count,
    v_snapshot_payload
  )
  ON CONFLICT (letter_id)
  DO NOTHING
  RETURNING id INTO v_snapshot_id;

  IF v_snapshot_id IS NULL THEN
    SELECT id INTO v_snapshot_id
    FROM comment_letter_approval_snapshots
    WHERE letter_id = p_letter_id;
  END IF;

  BEGIN
    PERFORM stage1a_emit_event(
      p_letter_id,
      'comment_letter.approved',
      jsonb_build_object(
        'letter_id', p_letter_id,
        'approved_by', p_approved_by,
        'approved_at', now()
      ),
      'stage1a-review-service',
      NULL
    );
  EXCEPTION WHEN unique_violation THEN
    -- Event already emitted for this letter/version; treat as idempotent success.
    NULL;
  END;

  UPDATE comment_letters
  SET extraction_status = 'completed',
      completed_at = now()
  WHERE id = p_letter_id;

  RETURN v_snapshot_id;
END
$$;

COMMIT;
