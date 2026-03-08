-- Stage 1A Slice 2 migration
-- Adds state transition guards and single-emission event dedupe for Stage 1A.
-- Does not change shared Stage 0 event names/envelope contracts.

BEGIN;

CREATE OR REPLACE FUNCTION stage1a_is_valid_transition(from_status text, to_status text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN from_status = to_status THEN true
    WHEN from_status = 'ingest_received' AND to_status = 'ocr_precheck' THEN true
    WHEN from_status = 'ocr_precheck' AND to_status IN ('ocr_processing', 'extracting_comments') THEN true
    WHEN from_status = 'ocr_processing' AND to_status IN ('extracting_comments', 'failed_extraction') THEN true
    WHEN from_status = 'extracting_comments' AND to_status IN ('normalizing_validating', 'failed_extraction') THEN true
    WHEN from_status = 'normalizing_validating' AND to_status IN ('review_queueing', 'failed_extraction') THEN true
    WHEN from_status = 'review_queueing' AND to_status IN ('human_review', 'approval_snapshot') THEN true
    WHEN from_status = 'human_review' AND to_status IN ('approval_snapshot', 'failed_extraction') THEN true
    WHEN from_status = 'approval_snapshot' AND to_status = 'completed' THEN true
    ELSE false
  END;
$$;

CREATE OR REPLACE FUNCTION stage1a_comment_letters_enforce_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.extraction_status IS DISTINCT FROM OLD.extraction_status THEN
    IF NOT stage1a_is_valid_transition(OLD.extraction_status, NEW.extraction_status) THEN
      RAISE EXCEPTION 'Invalid Stage 1A transition: % -> % for letter %', OLD.extraction_status, NEW.extraction_status, NEW.id;
    END IF;
  END IF;

  NEW.updated_at = now();
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_stage1a_comment_letters_transition ON comment_letters;
CREATE TRIGGER trg_stage1a_comment_letters_transition
BEFORE UPDATE ON comment_letters
FOR EACH ROW
EXECUTE FUNCTION stage1a_comment_letters_enforce_transition();

CREATE TABLE IF NOT EXISTS comment_letter_event_emissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  letter_id uuid NOT NULL REFERENCES comment_letters(id) ON DELETE CASCADE,
  event_type text NOT NULL CHECK (
    event_type IN (
      'comment_letter.parsing_started',
      'comment_letter.extraction_completed',
      'comment_letter.approved'
    )
  ),
  event_version integer NOT NULL DEFAULT 1 CHECK (event_version = 1),
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  emitted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (letter_id, event_type, event_version),
  UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_comment_letter_event_emissions_letter_emitted
  ON comment_letter_event_emissions(letter_id, emitted_at DESC);

COMMIT;
