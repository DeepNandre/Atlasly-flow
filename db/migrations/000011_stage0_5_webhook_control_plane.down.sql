BEGIN;

DROP FUNCTION IF EXISTS list_webhook_events(
  uuid,
  uuid,
  text,
  timestamptz,
  timestamptz,
  integer,
  integer
);

DROP FUNCTION IF EXISTS register_webhook_subscription(
  uuid,
  text,
  text[],
  text,
  uuid
);

DROP INDEX IF EXISTS webhook_deliveries_org_status_created_idx;
DROP INDEX IF EXISTS webhook_subscriptions_org_target_active_uidx;

ALTER TABLE webhook_subscriptions
  DROP CONSTRAINT IF EXISTS webhook_subscriptions_consecutive_failures_nonnegative_chk,
  DROP CONSTRAINT IF EXISTS webhook_subscriptions_event_types_allowed_chk,
  DROP CONSTRAINT IF EXISTS webhook_subscriptions_verification_status_chk,
  DROP CONSTRAINT IF EXISTS webhook_subscriptions_https_url_chk,
  DROP COLUMN IF EXISTS consecutive_failures,
  DROP COLUMN IF EXISTS last_delivery_at,
  DROP COLUMN IF EXISTS disabled_reason,
  DROP COLUMN IF EXISTS disabled_at,
  DROP COLUMN IF EXISTS verified_at,
  DROP COLUMN IF EXISTS verification_status;

DROP FUNCTION IF EXISTS is_allowed_webhook_event_types(jsonb);

COMMIT;
