# Stage 2 Slice 2 Rollback Runbook

## Scope
- Revert Slice 2 schema objects:
  - `ahj_requirements`
  - `application_field_mappings`
  - `connector_credentials`

## Preconditions
- Pause all write paths that use requirements ingestion, mapping updates, and connector credential updates.
- Export table contents if audit retention is required.

## Rollback steps
1. Disable writes for:
  - AHJ requirements ingestion workers.
  - Mapping management tools.
  - Connector credential management APIs.
2. Execute rollback SQL:
   - `db/migrations/rollback/000024_stage2_requirements_mappings_connectors_rollback.sql`
3. Validate:
   - All three tables are absent.
   - No pending migrations are left in partially-applied state.
4. Re-enable only fallback-safe code paths.

## Data impact
- Destructive rollback; all rows in Slice 2 tables are dropped.

## Contract safety note
- This rollback does not alter shared event names/versions or API route names.
