# Stage 3 Runtime Runbook

Date: 2026-03-03
Owner: Agent-6

## 1. Deployment Order
1. Apply DB migrations:
   - `db/migrations/000032_stage3_foundations.sql`
   - `db/migrations/000033_stage3_persistence_scaffolding.sql`
2. Deploy runtime modules:
   - `scripts/stage3/runtime_api.py`
   - `scripts/stage3/preflight_api.py`
   - `scripts/stage3/payout_api.py`
   - `scripts/stage3/finance_api.py`
   - `scripts/stage3/milestone_api.py`
3. Enable outbox publisher worker (`scripts/stage3/outbox_dispatcher.py`).
4. Enable provider webhook processing (`post_provider_webhook` flow).
5. Enable settlement ingestion/reconciliation run trigger.
6. Optional Stripe sandbox submission path:
   - Set `ATLASLY_STRIPE_SECRET_KEY`.
   - (Optional) override `ATLASLY_STRIPE_BASE_URL` for test/sandbox routing.

## 2. Pre-Flight Checks
- Execute Python test suite:
  - `python3 -m unittest tests/stage3/test_stage3_slice1_contracts.py ... tests/stage3/test_stage3_slice9_model_feature_pipeline.py`
- Execute DB contract test:
  - `scripts/db/test_stage3_slice6.sh`
- Verify deployed model exists and is in `deployed` state.
- Verify outbox table has unique constraint `(organization_id, idempotency_key, event_type)`.

## 3. Runtime Controls
- Financial endpoints require role `owner`/`admin` and step-up auth flag.
- Milestone verification requires role `owner`/`admin`/`pm` and full evidence payload.
- Outbox publishes only `publish_state='pending'` events.
- Reconciliation runs block cap increases if `run_status != matched`.
- Stripe providers (`stripe*`) auto-submit created instructions and transition to `submitted` only on accepted provider response.

## 4. Incident Playbooks
## Duplicate payout risk
- Action: freeze `POST /milestones/{milestoneId}/financial-actions` writes.
- Validate idempotency key collisions and outbox duplicates.
- Run reconciliation with latest provider settlements.
- If required, apply reversal flow (`instruction.reversed`).

## Reconciliation mismatch spike
- Action: pause high-value payout dispatch.
- Run settlement ingest + `POST /financial/reconciliation-runs` with fresh provider rows.
- Triage mismatch classes in order:
  - `missing_internal`
  - `amount_mismatch`
  - `duplicate_provider_event`
  - `missing_provider`
  - `timing_gap`

## Model anomaly
- Action: rollback model using model registry rollback path.
- Keep preflight endpoint online with deployed previous model.
- Continue emitting traceable score/recommendation events.

## 5. Rollback
1. Disable Stage 3 writers and workers.
2. If schema rollback needed:
   - `db/migrations/rollback/000033_stage3_persistence_scaffolding_rollback.sql`
   - `db/migrations/rollback/000032_stage3_foundations_rollback.sql`
3. Re-enable Stage 2-only runtime flows.

## 6. Post-Deploy Validation
- Trigger one preflight request and confirm:
  - response contains score/band/confidence/model version,
  - outbox contains `permit.preflight_scored`.
- Trigger one financial action and webhook settle sequence, then reconciliation run.
- Confirm `GET /financial/reconciliation-runs/{runId}` returns matched entry for instruction.
