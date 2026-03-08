-- Stage 1A Slice 1 migration
-- Dependencies: Stage 0 foundation tables are expected to exist:
-- organizations, projects, documents, users
-- This migration does not change shared Stage 0 enums/events/API contracts.

BEGIN;

CREATE TABLE IF NOT EXISTS comment_letters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  document_id uuid NOT NULL,
  created_by uuid NULL,
  extraction_status text NOT NULL DEFAULT 'ingest_received' CHECK (
    extraction_status IN (
      'ingest_received',
      'ocr_precheck',
      'ocr_processing',
      'extracting_comments',
      'normalizing_validating',
      'review_queueing',
      'human_review',
      'approval_snapshot',
      'completed',
      'failed_extraction'
    )
  ),
  page_count integer NULL CHECK (page_count IS NULL OR page_count > 0),
  source_filename text NULL,
  idempotency_key text NULL,
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  approved_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, document_id),
  UNIQUE (organization_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS comment_extractions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  comment_id text NOT NULL,
  letter_id uuid NOT NULL REFERENCES comment_letters(id) ON DELETE CASCADE,
  raw_text text NOT NULL CHECK (length(btrim(raw_text)) BETWEEN 20 AND 4000),
  discipline text NOT NULL CHECK (
    discipline IN (
      'structural',
      'electrical',
      'plumbing',
      'mechanical',
      'fire',
      'zoning',
      'civil',
      'architectural',
      'energy',
      'accessibility',
      'other'
    )
  ),
  severity text NOT NULL CHECK (severity IN ('critical', 'major', 'minor', 'info')),
  requested_action text NOT NULL CHECK (length(btrim(requested_action)) BETWEEN 10 AND 1000),
  code_reference text NOT NULL DEFAULT '',
  code_reference_jurisdiction text NOT NULL DEFAULT '',
  code_reference_family text NOT NULL DEFAULT 'UNKNOWN' CHECK (
    code_reference_family IN ('IBC', 'IRC', 'IECC', 'IFC', 'NEC', 'IPC', 'IMC', 'NFPA', 'LOCAL', 'UNKNOWN')
  ),
  code_reference_valid_format boolean NOT NULL DEFAULT false,
  page_number integer NOT NULL CHECK (page_number >= 1),
  citation_quote text NOT NULL CHECK (length(btrim(citation_quote)) BETWEEN 8 AND 600),
  citation_char_start integer NOT NULL CHECK (citation_char_start >= 0),
  citation_char_end integer NOT NULL CHECK (citation_char_end > citation_char_start),
  confidence_raw_text numeric(4,3) NOT NULL CHECK (confidence_raw_text >= 0 AND confidence_raw_text <= 1),
  confidence_discipline numeric(4,3) NOT NULL CHECK (confidence_discipline >= 0 AND confidence_discipline <= 1),
  confidence_severity numeric(4,3) NOT NULL CHECK (confidence_severity >= 0 AND confidence_severity <= 1),
  confidence_requested_action numeric(4,3) NOT NULL CHECK (confidence_requested_action >= 0 AND confidence_requested_action <= 1),
  confidence_code_reference numeric(4,3) NOT NULL CHECK (confidence_code_reference >= 0 AND confidence_code_reference <= 1),
  confidence_citation numeric(4,3) NOT NULL CHECK (confidence_citation >= 0 AND confidence_citation <= 1),
  confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  status text NOT NULL CHECK (
    status IN ('auto_accepted', 'needs_review', 'reviewed_corrected', 'approved_snapshot')
  ),
  normalization_flags text[] NOT NULL DEFAULT '{}'::text[],
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (letter_id, comment_id)
);

CREATE TABLE IF NOT EXISTS extraction_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  letter_id uuid NOT NULL REFERENCES comment_letters(id) ON DELETE CASCADE,
  extraction_id uuid NOT NULL REFERENCES comment_extractions(id) ON DELETE CASCADE,
  reviewer_id uuid NOT NULL,
  decision text NOT NULL CHECK (decision IN ('accepted', 'corrected', 'rejected')),
  correction_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  rationale text NOT NULL DEFAULT '',
  reviewed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extraction_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  letter_id uuid NOT NULL REFERENCES comment_letters(id) ON DELETE CASCADE,
  extraction_id uuid NULL REFERENCES comment_extractions(id) ON DELETE SET NULL,
  source text NOT NULL CHECK (source IN ('reviewer', 'system')),
  feedback_type text NOT NULL CHECK (
    feedback_type IN ('discipline_fix', 'severity_fix', 'action_fix', 'code_reference_fix', 'false_positive', 'false_negative', 'other')
  ),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Required Stage 1A indexes
CREATE INDEX IF NOT EXISTS idx_comment_extractions_letter_status
  ON comment_extractions(letter_id, status);

CREATE INDEX IF NOT EXISTS idx_comment_letters_project_created_at
  ON comment_letters(project_id, created_at DESC);

-- Helpful operational indexes
CREATE INDEX IF NOT EXISTS idx_comment_letters_org_status
  ON comment_letters(organization_id, extraction_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_reviews_letter_reviewed_at
  ON extraction_reviews(letter_id, reviewed_at DESC);

COMMIT;
