-- Slice 2 contract test: Stage 1B ticketing/routing invariants and idempotency guards.

DO $$
DECLARE
  owner_user uuid;
  worker_a uuid;
  worker_b uuid;
  org_id uuid;
  project_id uuid;
  doc_id uuid;
  letter_id uuid;
  approved_extraction_id uuid;
  unapproved_extraction_id uuid;
  task_id uuid;
  rule_id uuid;
  policy_id uuid;
BEGIN
  -- Required tables exist.
  IF to_regclass('public.routing_rules') IS NULL THEN
    RAISE EXCEPTION 'routing_rules missing';
  END IF;
  IF to_regclass('public.task_assignment_feedback') IS NULL THEN
    RAISE EXCEPTION 'task_assignment_feedback missing';
  END IF;
  IF to_regclass('public.assignment_escalations') IS NULL THEN
    RAISE EXCEPTION 'assignment_escalations missing';
  END IF;
  IF to_regclass('public.task_generation_runs') IS NULL THEN
    RAISE EXCEPTION 'task_generation_runs missing';
  END IF;

  -- Required task columns exist.
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'tasks'
      AND column_name = 'source_extraction_id'
  ) THEN
    RAISE EXCEPTION 'tasks.source_extraction_id missing';
  END IF;

  -- Required indexes exist.
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_tasks_org_source_extraction'
  ) THEN
    RAISE EXCEPTION 'ux_tasks_org_source_extraction missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='idx_domain_events_stage1b_pending'
  ) THEN
    RAISE EXCEPTION 'idx_domain_events_stage1b_pending missing';
  END IF;

  -- Seed identity/tenancy.
  INSERT INTO users(email, full_name) VALUES ('stage1b-owner@example.com', 'Stage1B Owner') RETURNING id INTO owner_user;
  INSERT INTO users(email, full_name) VALUES ('stage1b-worker-a@example.com', 'Stage1B Worker A') RETURNING id INTO worker_a;
  INSERT INTO users(email, full_name) VALUES ('stage1b-worker-b@example.com', 'Stage1B Worker B') RETURNING id INTO worker_b;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Stage1B Org', 'stage1b-org', owner_user)
  RETURNING id INTO org_id;

  INSERT INTO projects(id, organization_id, name, permit_type, status, created_by)
  VALUES (gen_random_uuid(), org_id, 'Project Alpha', 'commercial_ti', 'active', owner_user)
  RETURNING id INTO project_id;

  INSERT INTO documents(id, organization_id, project_id, latest_version_no, title, category, created_by)
  VALUES (gen_random_uuid(), org_id, project_id, 1, 'Letter Doc', 'plan_review', owner_user)
  RETURNING id INTO doc_id;

  INSERT INTO comment_letters(
    id, organization_id, project_id, document_id, created_by, extraction_status, started_at, completed_at, approved_at
  )
  VALUES (
    gen_random_uuid(), org_id, project_id, doc_id, owner_user, 'completed', now(), now(), now()
  )
  RETURNING id INTO letter_id;

  INSERT INTO comment_extractions(
    id, comment_id, letter_id, raw_text, discipline, severity, requested_action, code_reference,
    code_reference_jurisdiction, code_reference_family, code_reference_valid_format, page_number,
    citation_quote, citation_char_start, citation_char_end, confidence_raw_text, confidence_discipline,
    confidence_severity, confidence_requested_action, confidence_code_reference, confidence_citation, confidence, status
  )
  VALUES (
    gen_random_uuid(), 'c-approved-1', letter_id, 'Provide detail for structural anchor spacing near wall line.',
    'structural', 'major', 'Submit revised detail sheet with anchor spacing dimensions.',
    'IBC 1604.4', 'CA-LOCAL', 'IBC', true, 1, 'anchor spacing dimensions missing', 0, 32,
    0.92, 0.91, 0.90, 0.90, 0.89, 0.93, 0.91, 'approved_snapshot'
  )
  RETURNING id INTO approved_extraction_id;

  INSERT INTO comment_extractions(
    id, comment_id, letter_id, raw_text, discipline, severity, requested_action, code_reference,
    code_reference_jurisdiction, code_reference_family, code_reference_valid_format, page_number,
    citation_quote, citation_char_start, citation_char_end, confidence_raw_text, confidence_discipline,
    confidence_severity, confidence_requested_action, confidence_code_reference, confidence_citation, confidence, status
  )
  VALUES (
    gen_random_uuid(), 'c-unapproved-1', letter_id, 'Clarify panel schedule phase labeling.',
    'electrical', 'minor', 'Revise panel schedule labels for consistency.',
    'NEC 408.4', 'CA-LOCAL', 'NEC', true, 2, 'panel schedule labels', 0, 21,
    0.87, 0.86, 0.85, 0.86, 0.84, 0.88, 0.86, 'needs_review'
  )
  RETURNING id INTO unapproved_extraction_id;

  -- Approved extraction insert succeeds.
  INSERT INTO tasks(
    id, organization_id, project_id, title, description, discipline, status,
    assignee_user_id, priority, created_by, source_extraction_id, auto_assigned, assignment_confidence
  )
  VALUES (
    gen_random_uuid(), org_id, project_id, 'Resolve structural anchor spacing',
    'Generated from approved extraction', 'structural', 'todo',
    worker_a, 3, owner_user, approved_extraction_id, true, 0.9100
  )
  RETURNING id INTO task_id;

  -- Duplicate task for same extraction must fail.
  BEGIN
    INSERT INTO tasks(
      id, organization_id, project_id, title, description, discipline, status,
      assignee_user_id, priority, created_by, source_extraction_id, auto_assigned, assignment_confidence
    )
    VALUES (
      gen_random_uuid(), org_id, project_id, 'Duplicate extraction task',
      'Should fail', 'structural', 'todo',
      worker_a, 3, owner_user, approved_extraction_id, true, 0.9100
    );
    RAISE EXCEPTION 'expected unique violation for duplicate source_extraction_id';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Non-approved extraction must fail via trigger.
  BEGIN
    INSERT INTO tasks(
      id, organization_id, project_id, title, description, discipline, status,
      assignee_user_id, priority, created_by, source_extraction_id, auto_assigned, assignment_confidence
    )
    VALUES (
      gen_random_uuid(), org_id, project_id, 'Should fail unapproved extraction',
      'Should fail trigger', 'electrical', 'todo',
      worker_a, 3, owner_user, unapproved_extraction_id, true, 0.8200
    );
    RAISE EXCEPTION 'expected trigger rejection for non-approved extraction';
  EXCEPTION WHEN others THEN
    IF position('not approved_snapshot' in SQLERRM) = 0 THEN
      RAISE;
    END IF;
  END;

  -- Event dedupe: same (organization_id, idempotency_key) must fail.
  INSERT INTO domain_events(
    id, organization_id, aggregate_type, aggregate_id, event_type, event_version,
    idempotency_key, trace_id, occurred_at, payload, status
  )
  VALUES (
    gen_random_uuid(), org_id, 'comment_letter', letter_id, 'tasks.bulk_created_from_extractions', 1,
    'evt:stage1b:run:1', 'trace-stage1b-1', now(), '{"created_count":1}'::jsonb, 'pending'
  );

  BEGIN
    INSERT INTO domain_events(
      id, organization_id, aggregate_type, aggregate_id, event_type, event_version,
      idempotency_key, trace_id, occurred_at, payload, status
    )
    VALUES (
      gen_random_uuid(), org_id, 'comment_letter', letter_id, 'tasks.bulk_created_from_extractions', 1,
      'evt:stage1b:run:1', 'trace-stage1b-1b', now(), '{"created_count":1}'::jsonb, 'pending'
    );
    RAISE EXCEPTION 'expected domain_events duplicate idempotency_key failure';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Generation run dedupe: same (organization_id, idempotency_key) must fail.
  INSERT INTO task_generation_runs(
    organization_id, project_id, letter_id, idempotency_key, request_hash, status, created_count, existing_count, task_ids
  )
  VALUES (
    org_id, project_id, letter_id, 'run:stage1b:1', 'hash-a', 'COMPLETED', 1, 0, jsonb_build_array(task_id)
  );

  BEGIN
    INSERT INTO task_generation_runs(
      organization_id, project_id, letter_id, idempotency_key, request_hash, status, created_count, existing_count, task_ids
    )
    VALUES (
      org_id, project_id, letter_id, 'run:stage1b:1', 'hash-b', 'COMPLETED', 1, 0, jsonb_build_array(task_id)
    );
    RAISE EXCEPTION 'expected task_generation_runs duplicate idempotency_key failure';
  EXCEPTION WHEN unique_violation THEN
    NULL;
  END;

  -- Feedback integrity checks.
  INSERT INTO routing_rules(
    organization_id, project_id, is_active, priority, discipline, assignee_user_id, confidence_base, rule_hash, created_by, updated_by
  )
  VALUES (
    org_id, project_id, true, 10, 'structural', worker_a, 0.8500, 'rule-hash-1', owner_user, owner_user
  )
  RETURNING id INTO rule_id;

  BEGIN
    INSERT INTO task_assignment_feedback(
      organization_id, project_id, task_id, from_assignee_id, to_assignee_id,
      source_rule_id, source_confidence, feedback_reason_code, actor_user_id, was_auto_assigned
    )
    VALUES (
      org_id, project_id, task_id, worker_a, worker_a,
      rule_id, 0.9100, 'WRONG_DISCIPLINE', owner_user, true
    );
    RAISE EXCEPTION 'expected assignee change check to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    INSERT INTO task_assignment_feedback(
      organization_id, project_id, task_id, from_assignee_id, to_assignee_id,
      source_rule_id, source_confidence, feedback_reason_code, actor_user_id, was_auto_assigned
    )
    VALUES (
      org_id, project_id, task_id, worker_a, worker_b,
      rule_id, 0.9100, 'INVALID_REASON', owner_user, true
    );
    RAISE EXCEPTION 'expected feedback_reason_code check to fail';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  INSERT INTO task_assignment_feedback(
    organization_id, project_id, task_id, from_assignee_id, to_assignee_id,
    source_rule_id, source_confidence, feedback_reason_code, actor_user_id, was_auto_assigned
  )
  VALUES (
    org_id, project_id, task_id, worker_a, worker_b,
    rule_id, 0.9100, 'WRONG_DISCIPLINE', owner_user, true
  );

  -- SLA policy/escalation minimal write.
  INSERT INTO routing_sla_policies(
    organization_id, project_id, name, created_by, updated_by
  )
  VALUES (
    org_id, project_id, 'Default Policy', owner_user, owner_user
  )
  RETURNING id INTO policy_id;

  INSERT INTO assignment_escalations(
    organization_id, project_id, task_id, policy_id, current_level, assigned_at, ack_due_at, status
  )
  VALUES (
    org_id, project_id, task_id, policy_id, 1, now(), now() + interval '2 hours', 'OPEN'
  );
END $$;

SELECT
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ux_tasks_org_source_extraction'
  ) AS has_ux_tasks_org_source_extraction,
  EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='idx_domain_events_stage1b_pending'
  ) AS has_idx_domain_events_stage1b_pending;
