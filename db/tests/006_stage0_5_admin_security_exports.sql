-- Slice 6 contract tests: task templates + security audit exports admin controls.

DO $$
DECLARE
  owner_id uuid;
  admin_id uuid;
  pm_id uuid;
  org_id uuid;
  template_id uuid;
  template_id_2 uuid;
  export_id uuid;
  unauthorized_error text;
  duplicate_template_error text;
  export_status_value text;
BEGIN
  INSERT INTO users(email, full_name) VALUES ('slice6_owner@example.com', 'Slice 6 Owner') RETURNING id INTO owner_id;
  INSERT INTO users(email, full_name) VALUES ('slice6_admin@example.com', 'Slice 6 Admin') RETURNING id INTO admin_id;
  INSERT INTO users(email, full_name) VALUES ('slice6_pm@example.com', 'Slice 6 PM') RETURNING id INTO pm_id;

  INSERT INTO organizations(name, slug, created_by)
  VALUES ('Slice 6 Org', 'slice-6-org', owner_id)
  RETURNING id INTO org_id;

  INSERT INTO memberships(organization_id, workspace_id, user_id, role)
  VALUES (org_id, NULL, owner_id, 'owner');

  INSERT INTO memberships(organization_id, workspace_id, user_id, role)
  VALUES (org_id, NULL, admin_id, 'admin');

  INSERT INTO memberships(organization_id, workspace_id, user_id, role)
  VALUES (org_id, NULL, pm_id, 'pm');

  SELECT create_task_template(
    org_id,
    'Permit Intake Checklist',
    'Default template for intake',
    '{"steps":["collect docs","validate zoning"]}'::jsonb,
    owner_id
  ) INTO template_id;

  IF template_id IS NULL THEN
    RAISE EXCEPTION 'expected task template id';
  END IF;

  -- Duplicate active name in same org should fail.
  BEGIN
    PERFORM create_task_template(
      org_id,
      'Permit Intake Checklist',
      'Duplicate should fail',
      '{"steps":["x"]}'::jsonb,
      owner_id
    );
    RAISE EXCEPTION 'expected duplicate active template name to fail';
  EXCEPTION WHEN unique_violation THEN
    duplicate_template_error := 'ok';
  END;

  IF duplicate_template_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'active template name uniqueness check did not fire';
  END IF;

  PERFORM update_task_template(
    template_id,
    'Permit Intake Checklist',
    'Updated description',
    '{"steps":["collect docs","validate zoning","assign owner"]}'::jsonb,
    admin_id
  );

  PERFORM archive_task_template(template_id, admin_id);

  -- Same template name is allowed after archive (inactive old row).
  SELECT create_task_template(
    org_id,
    'Permit Intake Checklist',
    'Recreated after archive',
    '{"steps":["new"]}'::jsonb,
    owner_id
  ) INTO template_id_2;

  IF template_id_2 IS NULL THEN
    RAISE EXCEPTION 'expected recreated template id after archive';
  END IF;

  -- PM cannot request audit export.
  BEGIN
    PERFORM request_security_audit_export(
      org_id,
      pm_id,
      now() - interval '7 days',
      now(),
      'audit_timeline'
    );
    RAISE EXCEPTION 'expected PM audit export request to fail';
  EXCEPTION WHEN raise_exception THEN
    unauthorized_error := 'ok';
  END;

  IF unauthorized_error IS DISTINCT FROM 'ok' THEN
    RAISE EXCEPTION 'owner/admin gate did not fire for audit export';
  END IF;

  -- Owner request should succeed.
  SELECT request_security_audit_export(
    org_id,
    owner_id,
    now() - interval '30 days',
    now(),
    'audit_timeline'
  ) INTO export_id;

  IF export_id IS NULL THEN
    RAISE EXCEPTION 'expected security audit export id';
  END IF;

  PERFORM mark_security_audit_export_running(export_id, admin_id);

  PERFORM mark_security_audit_export_completed(
    export_id,
    admin_id,
    'sha256:abc123',
    's3://compliance-evidence/stage-0.5/CC7.2/report.json',
    'access-log-ref-1',
    now()
  );

  SELECT status
  INTO export_status_value
  FROM security_audit_exports
  WHERE id = export_id;

  IF export_status_value <> 'completed' THEN
    RAISE EXCEPTION 'expected completed export status, got %', export_status_value;
  END IF;
END $$;

-- Contract guard: shared permit_status remains unchanged.
SELECT
  EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'submitted'
  ) AS has_permit_status_submitted,
  EXISTS (
    SELECT 1 FROM pg_enum e
    JOIN pg_type t ON t.oid = e.enumtypid
    WHERE t.typname = 'permit_status' AND e.enumlabel = 'issued'
  ) AS has_permit_status_issued;
