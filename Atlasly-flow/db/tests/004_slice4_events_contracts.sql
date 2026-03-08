-- Slice 4 contract test: audit/domain event idempotency + audit append-only behavior.

DO $$
DECLARE
  u1 uuid;
  u2 uuid;
  org1 uuid;
  org2 uuid;
  ws1 uuid;
  ws2 uuid;
  p1 uuid;
  de1 uuid;
BEGIN
  INSERT INTO users(email, full_name) VALUES ('slice4-owner1@example.com', 'Slice4 Owner 1') RETURNING id INTO u1;
  INSERT INTO users(email, full_name) VALUES ('slice4-owner2@example.com', 'Slice4 Owner 2') RETURNING id INTO u2;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice4 Org One', 'slice4-org-one', u1)
  RETURNING id INTO org1;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice4 Org Two', 'slice4-org-two', u2)
  RETURNING id INTO org2;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org1, 'Default', true)
  RETURNING id INTO ws1;

  INSERT INTO workspaces(organization_id, name, is_default)
  VALUES (org2, 'Default', true)
  RETURNING id INTO ws2;

  INSERT INTO projects(organization_id, workspace_id, name, created_by)
  VALUES (org1, ws1, 'Slice4 Project', u1)
  RETURNING id INTO p1;

  INSERT INTO audit_events(
    organization_id,
    project_id,
    actor_user_id,
    action,
    entity_type,
    entity_id,
    request_id,
    trace_id,
    payload,
    event_hash
  ) VALUES (
    org1,
    p1,
    u1,
    'project.created',
    'project',
    p1,
    'req-slice4-1',
    'trace-slice4-1',
    '{"source":"test"}'::jsonb,
    'hash-1'
  );

  -- Audit table is append-only.
  BEGIN
    UPDATE audit_events
    SET action = 'project.updated'
    WHERE organization_id = org1
      AND request_id = 'req-slice4-1';
    RAISE EXCEPTION 'expected audit update to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    DELETE FROM audit_events
    WHERE organization_id = org1
      AND request_id = 'req-slice4-1';
    RAISE EXCEPTION 'expected audit delete to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  INSERT INTO domain_events(
    organization_id,
    aggregate_type,
    aggregate_id,
    event_type,
    event_version,
    idempotency_key,
    trace_id,
    occurred_at,
    payload
  ) VALUES (
    org1,
    'project',
    p1,
    'project.created',
    1,
    'req-slice4-1:project.created',
    'trace-slice4-1',
    now(),
    '{"project_id":"placeholder"}'::jsonb
  )
  RETURNING id INTO de1;

  -- Duplicate idempotency key in same org must fail.
  BEGIN
    INSERT INTO domain_events(
      organization_id,
      aggregate_type,
      aggregate_id,
      event_type,
      event_version,
      idempotency_key,
      trace_id,
      occurred_at,
      payload
    ) VALUES (
      org1,
      'project',
      p1,
      'project.created',
      1,
      'req-slice4-1:project.created',
      'trace-slice4-1-replay',
      now(),
      '{"project_id":"placeholder"}'::jsonb
    );
    RAISE EXCEPTION 'expected duplicate domain event idempotency key to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Same idempotency key in different org is allowed.
  INSERT INTO domain_events(
    organization_id,
    aggregate_type,
    aggregate_id,
    event_type,
    event_version,
    idempotency_key,
    trace_id,
    occurred_at,
    payload
  ) VALUES (
    org2,
    'project',
    ws2,
    'project.created',
    1,
    'req-slice4-1:project.created',
    'trace-slice4-org2',
    now(),
    '{"project_id":"org2-placeholder"}'::jsonb
  );

  INSERT INTO event_consumer_dedup(consumer_name, event_id)
  VALUES ('notification-consumer', de1);

  BEGIN
    INSERT INTO event_consumer_dedup(consumer_name, event_id)
    VALUES ('notification-consumer', de1);
    RAISE EXCEPTION 'expected consumer dedup duplicate to fail';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;
END $$;

SELECT
  EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'audit_events_no_update_trg'
  ) AS has_audit_no_update_trigger,
  EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'audit_events_no_delete_trg'
  ) AS has_audit_no_delete_trigger,
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'domain_events_pending_failed_idx'
  ) AS has_domain_events_pending_failed_idx;

