# Stage 0.5 Slice 4: Connector Runtime Lifecycle and Error Taxonomy

## Scope
- Add connector-run lifecycle constraints and transition functions.
- Add connector error taxonomy enforcement and retryability defaults.
- Add contract tests for run transitions and error classification behavior.
- Add rollback-tested runner for slice validation.

## Contract-change note
- No shared enums/events/API contracts were changed in this slice.
- This slice enforces internal connector runtime behavior behind existing Stage 0.5 interfaces.

## Delivered artifacts
- Migration up: `db/migrations/000013_stage0_5_connector_runtime.up.sql`
- Migration down: `db/migrations/000013_stage0_5_connector_runtime.down.sql`
- SQL tests: `db/tests/004_stage0_5_connector_runtime.sql`
- Runner: `scripts/db/test_slice4_stage0_5.sh`

## Operational behavior implemented
- Connector run constraints:
  - status values enforced (`queued|running|succeeded|partial|failed|cancelled`)
  - mode values enforced (`delta|full`)
  - trigger values enforced (`manual|scheduled|webhook|replay`)
  - lifecycle guard (terminal runs must have `ended_at`; active runs must not)
- Connector errors:
  - classification constrained to approved taxonomy
  - default retryability derived by classification
- Runtime functions:
  - `start_connector_run(...)`
  - `complete_connector_run(...)`
  - `record_connector_error(...)`

## Rollout plan
1. Apply Stage 0 and Stage 0.5 Slice 1-3 migrations.
2. Apply `000013_stage0_5_connector_runtime.up.sql`.
3. Run `scripts/db/test_slice4_stage0_5.sh` in CI/staging.
4. Enable connector runner code path to call runtime functions.

## Rollback plan
1. Disable connector runner write path.
2. Apply `000013_stage0_5_connector_runtime.down.sql`.
3. Keep prior Stage 0.5 schema in place unless full rollback required.
4. Verify no service calls remain to dropped runtime functions.

## Rollback risk notes
- Rollback removes lifecycle constraints and connector runtime helper functions.
- Existing connector runs/errors remain in tables, but operational guardrails are no longer enforced after rollback.
