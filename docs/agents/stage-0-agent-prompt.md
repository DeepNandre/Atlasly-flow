# Stage 0 Agent Prompt

Use the full content in `docs/agents/shared-context.md` as the first half of your prompt.

## Stage-specific mission
Focus on `docs/stages/stage-0-foundation.md`.

Perform deep research on how to execute Stage 0 production-grade:
- Multi-tenant architecture and RBAC patterns.
- Secure document storage/versioning and OCR pipeline orchestration.
- Event bus + audit log design with idempotency.
- Notification architecture and reliability patterns.
- PostgreSQL schema/index strategy for tenant isolation and scale.

Deliverables:
- Concrete implementation blueprint aligned to Stage 0 acceptance criteria.
- Recommended stack choices with rationale.
- Failure-mode analysis and operational runbooks for this stage.
