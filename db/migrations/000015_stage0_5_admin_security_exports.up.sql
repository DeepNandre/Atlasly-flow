BEGIN;

ALTER TABLE task_templates
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS archived_at timestamptz,
  ADD COLUMN IF NOT EXISTS archived_by uuid;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'task_templates_version_positive_chk'
  ) THEN
    ALTER TABLE task_templates
      ADD CONSTRAINT task_templates_version_positive_chk
      CHECK (version > 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'task_templates_template_object_chk'
  ) THEN
    ALTER TABLE task_templates
      ADD CONSTRAINT task_templates_template_object_chk
      CHECK (jsonb_typeof(template) = 'object');
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_task_templates_org_name_active
  ON task_templates (organization_id, lower(name))
  WHERE is_active;

ALTER TABLE security_audit_exports
  ADD COLUMN IF NOT EXISTS export_type text NOT NULL DEFAULT 'audit_timeline',
  ADD COLUMN IF NOT EXISTS started_at timestamptz,
  ADD COLUMN IF NOT EXISTS completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS failed_at timestamptz,
  ADD COLUMN IF NOT EXISTS failure_reason text,
  ADD COLUMN IF NOT EXISTS generated_by uuid;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'security_audit_exports_status_values_chk'
  ) THEN
    ALTER TABLE security_audit_exports
      ADD CONSTRAINT security_audit_exports_status_values_chk
      CHECK (status IN ('pending', 'running', 'completed', 'failed', 'expired'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'security_audit_exports_export_type_chk'
  ) THEN
    ALTER TABLE security_audit_exports
      ADD CONSTRAINT security_audit_exports_export_type_chk
      CHECK (export_type IN ('audit_timeline', 'access_log_bundle', 'compliance_evidence_pack'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_security_audit_exports_org_status_created
  ON security_audit_exports (organization_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_audit_exports_requested_by_created
  ON security_audit_exports (requested_by, created_at DESC);

CREATE OR REPLACE FUNCTION is_org_owner_or_admin(
  p_organization_id uuid,
  p_user_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM memberships m
    WHERE m.organization_id = p_organization_id
      AND m.user_id = p_user_id
      AND m.workspace_id IS NULL
      AND m.role IN ('owner', 'admin')
  );
$$;

CREATE OR REPLACE FUNCTION create_task_template(
  p_organization_id uuid,
  p_name text,
  p_description text,
  p_template jsonb,
  p_created_by uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_name IS NULL OR length(trim(p_name)) = 0 THEN
    RAISE EXCEPTION 'name is required';
  END IF;

  IF p_template IS NULL THEN
    RAISE EXCEPTION 'template is required';
  END IF;

  INSERT INTO task_templates (
    organization_id,
    name,
    description,
    template,
    is_active,
    version,
    created_by,
    updated_by,
    created_at,
    updated_at
  ) VALUES (
    p_organization_id,
    p_name,
    p_description,
    p_template,
    true,
    1,
    p_created_by,
    p_created_by,
    now(),
    now()
  )
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION update_task_template(
  p_template_id uuid,
  p_name text,
  p_description text,
  p_template jsonb,
  p_updated_by uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_template_id IS NULL THEN
    RAISE EXCEPTION 'template_id is required';
  END IF;

  UPDATE task_templates
  SET
    name = COALESCE(p_name, name),
    description = COALESCE(p_description, description),
    template = COALESCE(p_template, template),
    version = version + 1,
    updated_by = p_updated_by,
    updated_at = now()
  WHERE id = p_template_id
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'template % not found', p_template_id;
  END IF;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION archive_task_template(
  p_template_id uuid,
  p_archived_by uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  UPDATE task_templates
  SET
    is_active = false,
    archived_at = now(),
    archived_by = p_archived_by,
    updated_by = p_archived_by,
    updated_at = now()
  WHERE id = p_template_id
    AND is_active = true
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'template % not found or already archived', p_template_id;
  END IF;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION request_security_audit_export(
  p_organization_id uuid,
  p_requested_by uuid,
  p_time_range_start timestamptz,
  p_time_range_end timestamptz,
  p_export_type text DEFAULT 'audit_timeline'
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  IF p_organization_id IS NULL THEN
    RAISE EXCEPTION 'organization_id is required';
  END IF;

  IF p_requested_by IS NULL THEN
    RAISE EXCEPTION 'requested_by is required';
  END IF;

  IF p_time_range_start IS NULL OR p_time_range_end IS NULL THEN
    RAISE EXCEPTION 'time range is required';
  END IF;

  IF p_time_range_end < p_time_range_start THEN
    RAISE EXCEPTION 'time_range_end must be >= time_range_start';
  END IF;

  IF NOT is_org_owner_or_admin(p_organization_id, p_requested_by) THEN
    RAISE EXCEPTION 'user % is not permitted to request audit exports for org %', p_requested_by, p_organization_id;
  END IF;

  INSERT INTO security_audit_exports (
    organization_id,
    requested_by,
    generated_at,
    time_range_start,
    time_range_end,
    status,
    export_type,
    created_at,
    updated_at
  ) VALUES (
    p_organization_id,
    p_requested_by,
    NULL,
    p_time_range_start,
    p_time_range_end,
    'pending',
    p_export_type,
    now(),
    now()
  )
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION mark_security_audit_export_running(
  p_export_id uuid,
  p_generated_by uuid
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  UPDATE security_audit_exports
  SET
    status = 'running',
    started_at = now(),
    generated_by = p_generated_by,
    updated_at = now()
  WHERE id = p_export_id
    AND status = 'pending'
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'export % not found or not pending', p_export_id;
  END IF;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION mark_security_audit_export_completed(
  p_export_id uuid,
  p_generated_by uuid,
  p_checksum text,
  p_storage_uri text,
  p_access_log_ref text,
  p_generated_at timestamptz DEFAULT now()
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  UPDATE security_audit_exports
  SET
    status = 'completed',
    generated_by = p_generated_by,
    checksum = p_checksum,
    storage_uri = p_storage_uri,
    access_log_ref = p_access_log_ref,
    generated_at = p_generated_at,
    completed_at = now(),
    updated_at = now()
  WHERE id = p_export_id
    AND status IN ('pending', 'running')
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'export % not found or not completable', p_export_id;
  END IF;

  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION mark_security_audit_export_failed(
  p_export_id uuid,
  p_failure_reason text
)
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  v_id uuid;
BEGIN
  UPDATE security_audit_exports
  SET
    status = 'failed',
    failure_reason = p_failure_reason,
    failed_at = now(),
    updated_at = now()
  WHERE id = p_export_id
    AND status IN ('pending', 'running')
  RETURNING id INTO v_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'export % not found or not fail-able', p_export_id;
  END IF;

  RETURN v_id;
END;
$$;

COMMIT;
