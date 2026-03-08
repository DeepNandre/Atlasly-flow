-- Stage 2 Slice 2
-- Purpose: add AHJ requirements versioning, form-field mappings, and connector credential storage.
-- Contract safety: this migration does not rename/remove shared enums, events, or API paths.

begin;

-- AHJ requirements with version lineage and source provenance pointers.
create table if not exists ahj_requirements (
  id uuid primary key default gen_random_uuid(),
  ahj_id text not null,
  permit_type text not null,
  version_number integer not null,
  is_active boolean not null default true,
  supersedes_id uuid references ahj_requirements(id) on delete set null,
  requirements_json jsonb not null,
  source text not null,
  source_revision text,
  content_hash text not null,
  effective_at timestamptz not null default now(),
  expires_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (permit_type in ('commercial_ti', 'rooftop_solar', 'electrical_service_upgrade')),
  check (version_number > 0),
  check (char_length(content_hash) >= 32)
);

create unique index if not exists uq_ahj_requirements_ahj_permit_version
  on ahj_requirements (ahj_id, permit_type, version_number);

create unique index if not exists uq_ahj_requirements_single_active
  on ahj_requirements (ahj_id, permit_type)
  where is_active = true;

create index if not exists idx_ahj_requirements_lookup
  on ahj_requirements (ahj_id, permit_type, effective_at desc);

-- Canonical-to-template field mapping registry.
create table if not exists application_field_mappings (
  id uuid primary key default gen_random_uuid(),
  ahj_id text not null,
  permit_type text not null,
  form_template_id text not null,
  mapping_bundle_id text not null,
  mapping_version integer not null,
  canonical_field text not null,
  target_field_id text not null,
  target_field_type text not null default 'text',
  transform_rule jsonb,
  required boolean not null default false,
  default_value text,
  validation_regex text,
  effective_at timestamptz not null default now(),
  retired_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (permit_type in ('commercial_ti', 'rooftop_solar', 'electrical_service_upgrade')),
  check (mapping_version > 0),
  check (target_field_type in ('text', 'checkbox', 'radio', 'date', 'number', 'signature_placeholder')),
  check (retired_at is null or retired_at >= effective_at)
);

create unique index if not exists uq_app_field_mapping_unique_target
  on application_field_mappings (
    ahj_id, permit_type, form_template_id, mapping_version, canonical_field, target_field_id
  );

create index if not exists idx_app_field_mappings_template_lookup
  on application_field_mappings (form_template_id, mapping_version, canonical_field);

create index if not exists idx_app_field_mappings_ahj_permit_active
  on application_field_mappings (ahj_id, permit_type, effective_at desc)
  where retired_at is null;

-- Connector credential references scoped per organization.
-- Note: secrets are stored by reference only (credential_ref), never inline plaintext.
create table if not exists connector_credentials (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,
  connector text not null,
  ahj_id text,
  credential_ref text not null,
  scopes jsonb not null default '[]'::jsonb,
  status text not null default 'active',
  last_validated_at timestamptz,
  expires_at timestamptz,
  rotation_due_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (connector in ('accela_api', 'opengov_api', 'cloudpermit_portal_runner')),
  check (status in ('active', 'invalid', 'revoked', 'expired'))
);

create unique index if not exists uq_connector_credentials_org_connector_ahj
  on connector_credentials (organization_id, connector, coalesce(ahj_id, '__global__'));

create index if not exists idx_connector_credentials_org_connector
  on connector_credentials (organization_id, connector, created_at desc);

commit;
