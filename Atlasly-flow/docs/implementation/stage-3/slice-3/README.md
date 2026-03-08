# Stage 3 Slice 3

Status: Implemented
Date: 2026-03-03
Owner: Agent-6

## Scope
- Implement payout orchestration command handler skeleton for milestone-driven instruction creation.
- Enforce step-up auth, role gating, milestone-state gating, and idempotency-key replay behavior.
- Implement instruction failure-state transition guards for retry/terminal handling.
- Add unit tests for create/replay/reject and transition paths.

## Contract Safety
- No shared enum, event name, event envelope, or API path changes were introduced.
- `POST /milestones/{milestoneId}/financial-actions` remains unchanged.
- Canonical Stage 3 events remain unchanged; this slice emits `payout.instruction_created` v1 only.

## Files
- Handler module: `scripts/stage3/payout_api.py`
- Tests: `tests/stage3/test_stage3_slice3_payout_api.py`

## Rollback Notes
1. Revert code-only slice by removing the files listed above.
2. No database rollback is required for Slice 3.
3. Keep Slice 1 migrations/contracts and Slice 2 preflight module intact.
