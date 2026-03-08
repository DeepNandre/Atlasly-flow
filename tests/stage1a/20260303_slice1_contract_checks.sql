-- Stage 1A Slice 1 contract checks
-- Run with: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/stage1a/20260303_slice1_contract_checks.sql

DO $$
BEGIN
  IF to_regclass('public.comment_letters') IS NULL THEN
    RAISE EXCEPTION 'FAIL: table comment_letters missing';
  END IF;

  IF to_regclass('public.comment_extractions') IS NULL THEN
    RAISE EXCEPTION 'FAIL: table comment_extractions missing';
  END IF;

  IF to_regclass('public.extraction_reviews') IS NULL THEN
    RAISE EXCEPTION 'FAIL: table extraction_reviews missing';
  END IF;

  IF to_regclass('public.extraction_feedback') IS NULL THEN
    RAISE EXCEPTION 'FAIL: table extraction_feedback missing';
  END IF;
END
$$;

DO $$
DECLARE
  missing_required_columns integer;
BEGIN
  SELECT count(*) INTO missing_required_columns
  FROM (
    VALUES
      ('comment_extractions', 'comment_id'),
      ('comment_extractions', 'letter_id'),
      ('comment_extractions', 'raw_text'),
      ('comment_extractions', 'discipline'),
      ('comment_extractions', 'severity'),
      ('comment_extractions', 'requested_action'),
      ('comment_extractions', 'code_reference'),
      ('comment_extractions', 'page_number'),
      ('comment_extractions', 'confidence'),
      ('comment_extractions', 'status')
  ) AS req(table_name, column_name)
  WHERE NOT EXISTS (
    SELECT 1
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name = req.table_name
      AND c.column_name = req.column_name
  );

  IF missing_required_columns > 0 THEN
    RAISE EXCEPTION 'FAIL: missing required Stage 1A required columns in comment_extractions';
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'idx_comment_extractions_letter_status'
  ) THEN
    RAISE EXCEPTION 'FAIL: missing required index idx_comment_extractions_letter_status';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'idx_comment_letters_project_created_at'
  ) THEN
    RAISE EXCEPTION 'FAIL: missing required index idx_comment_letters_project_created_at';
  END IF;
END
$$;

SELECT 'PASS: Stage 1A Slice 1 contract checks completed' AS result;
