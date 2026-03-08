BEGIN;

CREATE TABLE notification_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id),
  channel notification_channel NOT NULL,
  template_key text NOT NULL,
  dedupe_key text NOT NULL,
  status notification_status NOT NULL DEFAULT 'pending',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  attempt_count integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  provider_message_id text NULL,
  last_error text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz NULL,
  CONSTRAINT notification_jobs_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT notification_jobs_org_dedupe_channel_unique UNIQUE (organization_id, dedupe_key, channel),
  CONSTRAINT notification_jobs_template_key_nonempty_chk CHECK (length(trim(template_key)) > 0),
  CONSTRAINT notification_jobs_dedupe_key_nonempty_chk CHECK (length(trim(dedupe_key)) > 0),
  CONSTRAINT notification_jobs_attempt_count_chk CHECK (attempt_count >= 0)
);

CREATE INDEX notification_jobs_org_id_id_idx
  ON notification_jobs (organization_id, id);

CREATE INDEX notification_jobs_status_next_attempt_idx
  ON notification_jobs (status, next_attempt_at)
  WHERE status IN ('pending', 'retry');

CREATE INDEX notification_jobs_user_created_at_idx
  ON notification_jobs (user_id, created_at DESC);

COMMIT;

