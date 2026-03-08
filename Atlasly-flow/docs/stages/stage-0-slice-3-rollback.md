# Stage 0 Slice 3 Rollback Notes

Date: 2026-03-03  
Scope: `000005_stage0_documents_and_versions` migration.

## What Slice 3 Adds

- Stage 0 document entities:
  - `documents`
  - `document_versions`
  - `document_tags`
- Document version sequencing enforcement:
  - `enforce_document_version_sequence()` trigger function
  - `document_versions_sequence_trg`
- OCR and virus-scan operational indexes for queueing paths.

## Rollback Order

1. `db/migrations/000005_stage0_documents_and_versions.down.sql`
2. If full rollback to pre-Slice 3 baseline is needed, continue with:
  - `db/migrations/000004_stage0_core_domain.down.sql`
  - `db/migrations/000003_stage0_identity_and_tenancy.down.sql`
  - `db/migrations/000002_stage0_create_types.down.sql`
  - `db/migrations/000001_stage0_enable_extensions.down.sql`

## Rollback Caveats

- Data loss: rolling back `0005` drops all document/version/tag data.
- Sequencing behavior: rollback removes trigger-based monotonic version enforcement.
- Dependency order: `0005` down must run before `0004` down because document tables depend on project tables.

## Pre-Rollback Checklist

1. Snapshot/backup database.
2. Disable document upload/version write paths.
3. Confirm no downstream migration has dependencies on `documents*` tables.
4. Execute `0005` down.
5. Re-run migration smoke checks on remaining Stage 0 schema objects.

