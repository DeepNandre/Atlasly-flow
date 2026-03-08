BEGIN;

CREATE TYPE membership_role AS ENUM (
  'owner',
  'admin',
  'pm',
  'reviewer',
  'subcontractor'
);

CREATE TYPE task_status AS ENUM (
  'todo',
  'in_progress',
  'blocked',
  'done'
);

-- Canonical cross-stage permit status contract (Task 3 locked values).
CREATE TYPE permit_status AS ENUM (
  'draft',
  'submitted',
  'in_review',
  'corrections_required',
  'approved',
  'issued',
  'expired'
);

CREATE TYPE document_ocr_status AS ENUM (
  'uploaded',
  'scanning',
  'queued_for_ocr',
  'processing',
  'completed',
  'failed'
);

CREATE TYPE notification_channel AS ENUM (
  'in_app',
  'email'
);

CREATE TYPE notification_status AS ENUM (
  'pending',
  'processing',
  'sent',
  'retry',
  'failed',
  'dead_letter'
);

CREATE TYPE event_status AS ENUM (
  'pending',
  'published',
  'failed',
  'dead_letter'
);

COMMIT;

