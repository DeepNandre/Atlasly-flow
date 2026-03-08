-- Stage 1A Slice 5 migration
-- Adds read-model functions aligned with GET endpoints:
--  - GET /comment-letters/{letterId}
--  - GET /comment-letters/{letterId}/extractions
-- No shared event/API contract name changes.

BEGIN;

CREATE OR REPLACE FUNCTION stage1a_get_comment_letter_status(
  p_letter_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_letter comment_letters%ROWTYPE;
  v_extraction_count integer;
  v_avg_confidence numeric(6,3);
  v_requires_review_count integer;
BEGIN
  SELECT * INTO v_letter
  FROM comment_letters
  WHERE id = p_letter_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Letter % not found', p_letter_id;
  END IF;

  SELECT
    count(*),
    coalesce(round(avg(confidence)::numeric, 3), 0),
    count(*) FILTER (WHERE status = 'needs_review')
  INTO v_extraction_count, v_avg_confidence, v_requires_review_count
  FROM comment_extractions
  WHERE letter_id = p_letter_id;

  RETURN jsonb_build_object(
    'letter_id', v_letter.id,
    'status', v_letter.extraction_status,
    'extraction_count', v_extraction_count,
    'avg_confidence', v_avg_confidence,
    'requires_review_count', v_requires_review_count,
    'approved_at', v_letter.approved_at,
    'completed_at', v_letter.completed_at,
    'created_at', v_letter.created_at,
    'updated_at', v_letter.updated_at
  );
END
$$;

CREATE OR REPLACE FUNCTION stage1a_list_comment_extractions(
  p_letter_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_letter_exists boolean;
  v_extractions jsonb;
BEGIN
  SELECT EXISTS(
    SELECT 1 FROM comment_letters WHERE id = p_letter_id
  ) INTO v_letter_exists;

  IF NOT v_letter_exists THEN
    RAISE EXCEPTION 'Letter % not found', p_letter_id;
  END IF;

  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'comment_id', ce.comment_id,
        'raw_text', ce.raw_text,
        'discipline', ce.discipline,
        'severity', ce.severity,
        'requested_action', ce.requested_action,
        'code_reference', ce.code_reference,
        'code_reference_jurisdiction', ce.code_reference_jurisdiction,
        'code_reference_family', ce.code_reference_family,
        'code_reference_valid_format', ce.code_reference_valid_format,
        'page_number', ce.page_number,
        'citation_quote', ce.citation_quote,
        'citation_char_start', ce.citation_char_start,
        'citation_char_end', ce.citation_char_end,
        'confidence', ce.confidence,
        'status', ce.status,
        'normalization_flags', ce.normalization_flags,
        'created_at', ce.created_at,
        'updated_at', ce.updated_at
      )
      ORDER BY ce.page_number, ce.comment_id
    ),
    '[]'::jsonb
  ) INTO v_extractions
  FROM comment_extractions ce
  WHERE ce.letter_id = p_letter_id;

  RETURN jsonb_build_object(
    'letter_id', p_letter_id,
    'extractions', v_extractions
  );
END
$$;

CREATE OR REPLACE FUNCTION stage1a_get_approval_snapshot(
  p_letter_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_snapshot comment_letter_approval_snapshots%ROWTYPE;
BEGIN
  SELECT * INTO v_snapshot
  FROM comment_letter_approval_snapshots
  WHERE letter_id = p_letter_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Approval snapshot for letter % not found', p_letter_id;
  END IF;

  RETURN jsonb_build_object(
    'snapshot_id', v_snapshot.id,
    'letter_id', v_snapshot.letter_id,
    'approved_by', v_snapshot.approved_by,
    'approved_at', v_snapshot.approved_at,
    'extraction_count', v_snapshot.extraction_count,
    'snapshot_payload', v_snapshot.snapshot_payload
  );
END
$$;

COMMIT;
