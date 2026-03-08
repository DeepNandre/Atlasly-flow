BEGIN;

CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id uuid NULL,
  actor_user_id uuid NULL REFERENCES users(id),
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  request_id text NOT NULL,
  trace_id text NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  prev_hash text NULL,
  event_hash text NOT NULL,
  immutable boolean NOT NULL DEFAULT true,
  CONSTRAINT audit_events_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT audit_events_project_fk
    FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id),
  CONSTRAINT audit_events_action_nonempty_chk CHECK (length(trim(action)) > 0),
  CONSTRAINT audit_events_entity_type_nonempty_chk CHECK (length(trim(entity_type)) > 0),
  CONSTRAINT audit_events_request_id_nonempty_chk CHECK (length(trim(request_id)) > 0),
  CONSTRAINT audit_events_event_hash_nonempty_chk CHECK (length(trim(event_hash)) > 0)
);

CREATE TABLE domain_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  aggregate_type text NOT NULL,
  aggregate_id uuid NOT NULL,
  event_type text NOT NULL,
  event_version integer NOT NULL,
  idempotency_key text NOT NULL,
  trace_id text NULL,
  occurred_at timestamptz NOT NULL,
  payload jsonb NOT NULL,
  status event_status NOT NULL DEFAULT 'pending',
  publish_attempts integer NOT NULL DEFAULT 0,
  published_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT domain_events_org_id_id_unique UNIQUE (organization_id, id),
  CONSTRAINT domain_events_org_idempotency_unique UNIQUE (organization_id, idempotency_key),
  CONSTRAINT domain_events_aggregate_type_nonempty_chk CHECK (length(trim(aggregate_type)) > 0),
  CONSTRAINT domain_events_event_type_nonempty_chk CHECK (length(trim(event_type)) > 0),
  CONSTRAINT domain_events_idempotency_key_nonempty_chk CHECK (length(trim(idempotency_key)) > 0),
  CONSTRAINT domain_events_event_version_chk CHECK (event_version > 0),
  CONSTRAINT domain_events_publish_attempts_chk CHECK (publish_attempts >= 0)
);

CREATE TABLE event_consumer_dedup (
  consumer_name text NOT NULL,
  event_id uuid NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_name, event_id),
  CONSTRAINT event_consumer_dedup_consumer_name_nonempty_chk CHECK (length(trim(consumer_name)) > 0),
  CONSTRAINT event_consumer_dedup_event_fk
    FOREIGN KEY (event_id)
    REFERENCES domain_events(id)
    ON DELETE CASCADE
);

CREATE INDEX audit_events_org_id_id_idx
  ON audit_events (organization_id, id);

CREATE INDEX audit_events_project_timeline_idx
  ON audit_events (project_id, occurred_at DESC, id DESC);

CREATE INDEX audit_events_org_timeline_idx
  ON audit_events (organization_id, occurred_at DESC, id DESC);

CREATE INDEX domain_events_org_id_id_idx
  ON domain_events (organization_id, id);

CREATE INDEX domain_events_pending_failed_idx
  ON domain_events (status, created_at)
  WHERE status IN ('pending', 'failed');

CREATE INDEX domain_events_aggregate_idx
  ON domain_events (organization_id, aggregate_type, aggregate_id, occurred_at DESC);

CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION
    'audit_events is append-only'
    USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER audit_events_no_update_trg
  BEFORE UPDATE ON audit_events
  FOR EACH ROW
  EXECUTE FUNCTION prevent_audit_event_mutation();

CREATE TRIGGER audit_events_no_delete_trg
  BEFORE DELETE ON audit_events
  FOR EACH ROW
  EXECUTE FUNCTION prevent_audit_event_mutation();

COMMIT;

