BEGIN;

DROP FUNCTION IF EXISTS request_webhook_replay_for_dead_letter(uuid, uuid, text);
DROP FUNCTION IF EXISTS enqueue_webhook_retry(uuid, text, text, integer);
DROP FUNCTION IF EXISTS webhook_failure_is_retryable(integer, text);
DROP FUNCTION IF EXISTS webhook_retry_delay_seconds(integer);

DROP INDEX IF EXISTS idx_webhook_replay_jobs_org_status_created;
DROP INDEX IF EXISTS idx_webhook_dead_letters_org_dead_lettered_at;
DROP INDEX IF EXISTS idx_webhook_deliveries_retry_queue;

ALTER TABLE webhook_deliveries
  DROP CONSTRAINT IF EXISTS webhook_deliveries_retry_count_chk,
  DROP CONSTRAINT IF EXISTS webhook_deliveries_max_attempts_chk,
  DROP CONSTRAINT IF EXISTS webhook_deliveries_status_chk,
  DROP COLUMN IF EXISTS is_terminal,
  DROP COLUMN IF EXISTS retry_count,
  DROP COLUMN IF EXISTS max_attempts,
  DROP COLUMN IF EXISTS terminal_at,
  DROP COLUMN IF EXISTS last_attempt_at,
  DROP COLUMN IF EXISTS first_attempt_at;

DROP TABLE IF EXISTS webhook_replay_jobs;
DROP TABLE IF EXISTS webhook_dead_letters;

COMMIT;
