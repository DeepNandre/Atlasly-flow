# Staged Delivery Plan

This directory breaks down the canonical PRD in [`../master-prd.md`](../master-prd.md) into implementation-ready stage specifications.

## Build order
1. [Stage 0 - Foundation](./stage-0-foundation.md)
2. [Stage 0.5 - Enterprise Readiness](./stage-0.5-enterprise-readiness.md)
3. [Stage 1A - Comment Extraction](./stage-1a-comment-extraction.md)
4. [Stage 1B - Ticketing and Routing](./stage-1b-ticketing-routing.md)
5. [Stage 2 - Parity (Intake, Autofill, Sync)](./stage-2-parity-intake-autofill-sync.md)
6. [Stage 3 - Moat (Predictive + Fintech)](./stage-3-moat-predictive-fintech.md)

## Hard gates
- Stage 1A is blocked until Stage 0 audit, event, and document primitives are complete.
- Stage 2 is blocked until Stage 1B routing feedback loop is live.
- Stage 3 is blocked until Stage 2 normalized permit status events are stable.
- Enforced gate runner: `scripts/mvp-gates.sh` (runs stage suites in build order plus control-tower checks).

## Shared terminology
- AHJ: Authority Having Jurisdiction.
- Permit status states: `submitted`, `in_review`, `corrections_required`, `approved`, `issued`, `expired`.
- Routing rules: discipline and project-role mappings that assign extracted issues to internal and external owners.

## Validation checklist
- Each stage file includes all required sections: Title, Goal, Scope (In), Out of Scope, Dependencies, Data model changes, APIs/interfaces, Operational requirements, Acceptance criteria, Risks and mitigations, Milestones.
- Each stage file includes explicit API/event/type details: REST endpoints, event contracts, schema changes, security constraints.
- Each stage file includes at least one measurable KPI and explicit exit criteria.
- Stage files do not reference undefined tables, endpoints, or events.
- Links in this index resolve correctly.

## Source of truth
- Canonical PRD: [`../master-prd.md`](../master-prd.md)
- These stage docs are implementation-ready specifications derived from the canonical PRD.
