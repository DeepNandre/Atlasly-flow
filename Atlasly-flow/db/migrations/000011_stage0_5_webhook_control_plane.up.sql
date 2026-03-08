BEGIN;

-- Allowed outbound events for Stage 0/0.5 webhook subscriptions.
CREATE OR REPLACE FUNCTION is_allowed_webhook_event_types(event_types jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT
    jsonb_typeof(event_types) = 'array'
    AND jsonb_array_length(event_types) > 0
    AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(event_types) AS e(event_name)
      WHERE e.event_name NOT IN (
        'document.uploaded',
        'document.ocr_completed',
        'task.created',
        'task.assigned',
        'permit.status_changed',
        'integration.run_started',
        'integration.run_completed',
        'webhook.delivery_failed'
      )
    );
$$;

ALTER TABLE webhook_subscriptions
  ADD COLUMN IF NOT EXISTS verification_status text NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS verified_at timestamptz,
  ADD COLUMN IF NOT EXISTS disabled_at timestamptz,
  ADD COLUMN IF NOT EXISTS disabled_reason text,
  ADD COLUMN IF NOT EXISTS last_delivery_at timestamptz,
  ADD COLUMN IF NOT EXISTS consecutive_failures integer NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_subscriptions_https_url_chk'
  ) THEN
    ALTER TABLE webhook_subscriptions
      ADD CONSTRAINT webhook_subscriptions_https_url_chk
      CHECK (target_url ~* '^https://');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_subscriptions_verification_status_chk'
  ) THEN
    ALTER TABLE webhook_subscriptions
      ADD CONSTRAINT webhook_subscriptions_verification_status_chk
      CHECK (verification_status IN ('pending', 'verified', 'failed', 'disabled'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_subscriptions_event_types_allowed_chk'
  ) THEN
    ALTER TABLE webhook_subscriptions
      ADD CONSTRAINT webhook_subscriptions_event_types_allowed_chk
      CHECK (is_allowed_webhook_event_types(event_types));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'webhook_subscriptions_consecutive_failures_nonnegative_chk'
  ) THEN
    ALTER TABLE webhook_subscriptions
      ADD CONSTRAINT webhook_subscriptions_consecutive_failures_nonnegative_chk
      CHECK (consecutive_failures >= 0);
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS webhook_subscriptions_org_target_active_uidx
  ON webhook_subscriptions (organization_id, target_url)
  WHERE is_active;

CREATE INDEX IF NOT EXISTS webhook_deliveries_org_status_created_idx
  ON webhook_deliveries (organization_id, status, created_at DESC);

CREATE OR REPLACE FUNCTION register_webhook_subscription(
  p_organization_id uuid,
  p_target_url text,
  p_event_types text[],
  p_signing_secret_ciphertext text,
  p_created_by uuid DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
  v_event_types jsonb;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_target_url IS NULL OR length(trim(p_target_url)) = 0 THEN
    RAISE EXCEPTION 'target_url is required';
  END IF;

  IF p_signing_secret_ciphertext IS NULL OR length(trim(p_signing_secret_ciphertext)) = 0 THEN
    RAISE EXCEPTION 'signing_secret_ciphertext is required';
  END IF;

  IF p_event_types IS NULL OR array_length(p_event_types, 1) IS NULL THEN
    RAISE EXCEPTION 'event_types must not be empty';
  END IF;

  v_event_types := to_jsonb(p_event_types);

  INSERT INTO webhook_subscriptions (
    organization_id,
    target_url,
    event_types,
    signing_secret_ciphertext,
    created_by,
    updated_by,
    verification_status,
    is_active
  ) VALUES (
    p_organization_id,
    p_target_url,
    v_event_types,
    p_signing_secret_ciphertext,
    p_created_by,
    p_created_by,
    'pending',
    true
  )
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION list_webhook_events(
  p_organization_id uuid,
  p_subscription_id uuid DEFAULT NULL,
  p_status text DEFAULT NULL,
  p_from timestamptz DEFAULT NULL,
  p_to timestamptz DEFAULT NULL,
  p_limit integer DEFAULT 100,
  p_offset integer DEFAULT 0
)
RETURNS TABLE (
  delivery_id uuid,
  subscription_id uuid,
  event_id uuid,
  event_name text,
  attempt integer,
  status text,
  response_code integer,
  error_code text,
  created_at timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    d.id,
    d.subscription_id,
    d.event_id,
    d.event_name,
    d.attempt,
    d.status,
    d.response_code,
    d.error_code,
    d.created_at
  FROM webhook_deliveries d
  WHERE d.organization_id = p_organization_id
    AND (p_subscription_id IS NULL OR d.subscription_id = p_subscription_id)
    AND (p_status IS NULL OR d.status = p_status)
    AND (p_from IS NULL OR d.created_at >= p_from)
    AND (p_to IS NULL OR d.created_at <= p_to)
  ORDER BY d.created_at DESC
  LIMIT GREATEST(1, LEAST(p_limit, 500))
  OFFSET GREATEST(p_offset, 0);
$$;

COMMIT;
