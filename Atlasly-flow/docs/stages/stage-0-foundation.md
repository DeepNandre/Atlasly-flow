# Stage 0: Foundation

## Title
Stage 0: Core Platform Foundation

## Goal
Establish the multi-tenant core platform, canonical permit workflow objects, and secure event/audit infrastructure required by all subsequent stages.

## Scope (In)
- Multi-tenant org/workspace model with RBAC roles: `owner`, `admin`, `pm`, `reviewer`, `subcontractor`.
- Identity and auth baseline with SSO-ready abstraction.
- Core entities: projects, permits, tasks, documents, comments, assignments, AHJ profiles.
- Document upload/version metadata and OCR processing state.
- Workflow pipeline states: `todo`, `in_progress`, `blocked`, `done`.
- Immutable audit timeline and event bus primitives.
- Notification primitives (in-app + email trigger path).

## Out of Scope
- AI parsing and extraction.
- External AHJ portal connectors.
- Form autofill generation.
- Fintech payout logic.

## Dependencies
- PostgreSQL with tenant-safe schema design.
- Object storage bucket for documents.
- Queue/runtime for asynchronous events.
- Email provider for notification delivery.

## Data model changes

### Schema changes
- New tables: `organizations`, `workspaces`, `users`, `memberships`, `projects`, `permits`, `tasks`, `task_comments`, `documents`, `document_versions`, `document_tags`, `project_contacts`, `ahj_profiles`, `audit_events`, `domain_events`, `notification_jobs`.
- New tables for future moat instrumentation: `permit_reviews`, `ahj_comments`, `code_citations`, `review_outcomes`.
- Indexes:
  - Composite: `(organization_id, id)` for all tenant-owned tables.
  - Search: `(project_id, status)` on `permits` and `tasks`.
  - Timeline: `(project_id, created_at)` on `audit_events`.

## APIs / interfaces

### REST endpoints
- `POST /orgs`: create organization and default workspace.
- `POST /orgs/{orgId}/users`: invite user with role.
- `POST /projects`: create project with AHJ metadata shell.
- `POST /projects/{projectId}/documents`: upload document and metadata.
- `POST /projects/{projectId}/tasks`: create task.
- `PATCH /tasks/{taskId}`: update status/assignee/due date.
- `GET /projects/{projectId}/timeline`: return audit timeline.

### Event contracts
- Producer: document service -> `document.uploaded` with `document_id`, `project_id`, `uploader_id`, `version`, `uploaded_at`.
- Producer: document processing worker -> `document.ocr_completed` with `document_id`, `ocr_status`, `page_count`, `completed_at`.
- Producer: task service -> `task.created` with `task_id`, `project_id`, `discipline`, `created_by`.
- Producer: task service -> `task.assigned` with `task_id`, `assignee_id`, `assigned_by`, `assigned_at`.
- Producer: permit service -> `permit.status_changed` with `permit_id`, `old_status`, `new_status`, `source`, `changed_at`.

### Security constraints
- Tenant boundary enforced on every data access by `organization_id`.
- RBAC checks required for every mutating endpoint.
- Service-to-service events signed and verified.
- Audit table append-only for non-system-admin actors.

## Operational requirements
- 99.9% monthly API availability target.
- End-to-end audit logging for all writes.
- Background workers with retry/backoff and dead-letter queue.
- Document upload virus scan and MIME validation.

## Acceptance criteria
- KPI: 100% pass on tenant-isolation integration tests.
- KPI: p95 project timeline query latency <= 300 ms for 10k events.
- Exit criteria: project -> permit -> task -> document lifecycle fully usable without AI features.
- Exit criteria: every write action emits audit event and, where applicable, domain event.

## Risks and mitigations
- Risk: cross-tenant leakage.
  - Mitigation: row-level tenancy checks in application and DB policy tests.
- Risk: event duplication.
  - Mitigation: idempotency key per event and consumer dedupe table.
- Risk: document processing backlog.
  - Mitigation: queue partitioning by organization and autoscaling workers.

## Milestones (Week-by-week)
- Week 1: tenancy model, RBAC matrix, auth scaffolding.
- Week 2: core schemas and migrations, project and permit CRUD.
- Week 3: document/version service and storage integration.
- Week 4: task workflow + assignment + comments.
- Week 5: audit and domain event pipelines.
- Week 6: notifications, load tests, security hardening, release gate.
