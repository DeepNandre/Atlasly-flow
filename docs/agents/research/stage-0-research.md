# Stage 0 Research

Status: In Progress
Owner: Stage 0 Agent
Last Updated: 2026-03-02

## 1. Stage objective recap
- Establish a tenant-safe, RBAC-enforced platform foundation for organizations, workspaces, users, and canonical permit workflow entities.
- Deliver reliable document ingest/versioning with secure storage, malware/MIME controls, and OCR pipeline state orchestration.
- Implement immutable audit + domain event primitives with idempotent producers/consumers and traceable write lineage.
- Ship in-app/email notification primitives and meet Stage 0 reliability + performance acceptance criteria.

## 2. Deep research findings

### Architecture
- Tenant isolation: Use defense-in-depth with `organization_id` on every tenant-owned record, DB row-level security (RLS), and app-level query scoping. Enforce `(organization_id, id)` composite uniqueness/indexing for fast scoped lookups and leakage prevention.
- Auth and identity: Keep provider-agnostic auth boundary (OIDC/SAML-ready) with an internal user identity table and external identity mapping table. This avoids lock-in and supports enterprise SSO in later stages.
- RBAC: Model organization-level role memberships with optional workspace-level overrides. Resolve effective permissions server-side through a permission matrix instead of hardcoded endpoint checks.
- Eventing: Use transactional outbox pattern for `domain_events` to guarantee event emission consistency with writes. Consumers use dedupe keys (`event_id` or producer idempotency key) in a `consumer_offsets`/`event_dedup` table.
- Audit immutability: Append-only `audit_events` table with cryptographic hash chaining (`prev_hash`, `event_hash`) for tamper evidence, plus admin-only retention/export controls.

### Tooling
- Database: PostgreSQL 16+ with partitioning candidates for high-write tables (`audit_events`, `domain_events`, `notification_jobs`) by time and/or organization tier.
- Queue/runtime: Managed queue with DLQ + exponential backoff (e.g., SQS, RabbitMQ, or pgmq if keeping infra minimal). Partition dispatch by `organization_id` to contain noisy-tenant impact.
- Document storage: S3-compatible object store with per-org key prefixes, object versioning, server-side encryption, signed upload URLs, and upload-complete callback.
- OCR pipeline: Async worker flow `uploaded -> scanning -> queued_for_ocr -> processing -> completed|failed`, with retry budget and terminal failure reason taxonomy.
- Notifications: Provider abstraction over email vendor (SES/SendGrid/Postmark) and in-app notifications table, with idempotent send keys and provider response logging.

### Operations
- Availability target (99.9%) requires health probes, queue depth alerts, retry/DLQ dashboards, and backup/restore drills.
- Timeline p95 <= 300 ms at 10k events likely needs tight indexes (`project_id, created_at DESC`) and keyset pagination; avoid offset pagination for deep timelines.
- Observability baseline: structured logs with `trace_id`, `organization_id`, `actor_id`, `request_id`; metrics for queue lag, OCR latency, event publish delay, notification failures.
- Security controls: mandatory MIME allowlist, antivirus scanning before durable availability, least-privilege IAM for workers/storage, event signature verification for service-to-service trust.

### Risks
- Cross-tenant leakage via missing where-clause or joins.
  - Mitigation: RLS, policy tests, scoped repositories, static query lint rules for tenant tables.
- Event duplication/out-of-order processing.
  - Mitigation: producer idempotency keys, consumer dedupe table, versioned event contracts, monotonic sequence per aggregate where needed.
- OCR backlog and SLA breaches.
  - Mitigation: per-tenant queue partitioning, worker autoscaling, max-attempt + DLQ workflows with operator playbook.
- Notification spam or drop.
  - Mitigation: dedupe keys, provider webhook reconciliation, suppression list support, retry policies by error class.

## 3. Recommended implementation approach
1. Define tenancy + RBAC contract first.
   - Finalize role-permission matrix for `owner`, `admin`, `pm`, `reviewer`, `subcontractor`.
   - Implement membership model and policy engine interface.
2. Build foundational schema + migrations.
   - Create all Stage 0 tables with FKs, constraints, enums/states, and required composite indexes.
   - Enable RLS policies and add policy regression tests before API development.
3. Implement auth/org/project baseline APIs.
   - Ship `POST /orgs`, org invites, project creation, and permit/task scaffolding with RBAC guards.
4. Implement document ingest/versioning.
   - Signed upload flow, object metadata capture, `documents` + `document_versions`, virus/MIME scan gate, OCR status transitions.
5. Implement workflow/task mutation path.
   - `POST /projects/{projectId}/tasks`, `PATCH /tasks/{taskId}`, comment/assignment flow with invariant checks.
6. Add audit + domain events via outbox.
   - Emit audit on every write and domain events where contract requires; publish worker with retries + DLQ.
7. Add notification primitives.
   - In-app notification persistence + email trigger path with idempotent send keys.
8. Harden and validate for release gate.
   - Isolation integration tests, latency/load tests, incident runbooks, rollback playbook, release checklist.

## 4. Required APIs/data/contracts and schema guidance

### API contract guidance
- `POST /orgs`: idempotent by external request key; returns org + default workspace + creator membership.
- `POST /orgs/{orgId}/users`: invite semantics, role validation, duplicate invite conflict handling.
- `POST /projects`: validates org/workspace access and writes initial AHJ metadata shell.
- `POST /projects/{projectId}/documents`: creates pending document version record before upload completion callback.
- `PATCH /tasks/{taskId}`: optimistic concurrency (`version` or `updated_at` precondition) to avoid lost updates.
- `GET /projects/{projectId}/timeline`: keyset pagination on `(created_at, id)` and optional event-type filters.

### Event contract guidance
- Common envelope for all events:
  - `event_id`, `event_type`, `event_version`, `organization_id`, `aggregate_type`, `aggregate_id`, `occurred_at`, `produced_by`, `idempotency_key`, `trace_id`, `payload`.
- Required Stage 0 events:
  - `document.uploaded`
  - `document.ocr_completed`
  - `task.created`
  - `task.assigned`
  - `permit.status_changed`
- Consumer contract:
  - Must persist processed `event_id`/`idempotency_key` before side effects commit.
  - Must tolerate replay and out-of-order delivery.

### Schema/index guidance
- Tenant-owned tables include `organization_id NOT NULL` and composite index `(organization_id, id)`.
- Core performance indexes:
  - `permits(project_id, status)`
  - `tasks(project_id, status)`
  - `audit_events(project_id, created_at DESC, id DESC)`
  - `domain_events(published_at NULLS FIRST, occurred_at)` for outbox scanning.
- Add partial indexes:
  - `notification_jobs(status, next_attempt_at)` where `status IN ('pending','retry')`.
  - `document_versions(ocr_status, created_at)` where `ocr_status IN ('queued_for_ocr','processing')`.

## 5. Build-vs-buy decisions and tradeoffs
- Auth provider:
  - Buy (managed identity) now for speed/security; keep internal identity abstraction to avoid lock-in.
- Object storage + AV scanning:
  - Buy managed object storage; build lightweight scanning orchestration to keep control of policy and auditability.
- Queue:
  - Buy managed queue if cloud-native ops preferred; build with Postgres queue only if minimizing infra surface outweighs throughput flexibility.
- Notification delivery:
  - Buy email provider transport; build notification orchestration and templates in-house for product control.
- Event bus:
  - Build outbox + contracts in-house (core platform moat and correctness-critical), optionally buy broker operations.

## 6. Validation and test plan
- Tenant isolation tests:
  - Positive/negative integration tests for every tenant-owned endpoint and direct DB policy tests for RLS.
- RBAC matrix tests:
  - Table-driven tests validating each role against each mutating action.
- Contract tests:
  - Event schema validation and backward compatibility checks for versioned payloads.
- Reliability tests:
  - Retry/DLQ simulations for OCR and notification workers; verify alerting and replay procedures.
- Performance tests:
  - Seed project timelines with 10k+ events; verify `GET /timeline` p95 <= 300 ms with realistic filters.
- Security tests:
  - MIME spoof attempts, malware upload path, signed URL expiry misuse, event signature tamper tests.

## 7. Execution checklist
1. Finalize RBAC permission matrix and tenancy invariants.
2. Author schema migration set for Stage 0 tables + indexes + constraints.
3. Enable RLS and ship policy test harness.
4. Implement org/workspace/user/membership services + APIs.
5. Implement project/permit/task/comment core CRUD with RBAC enforcement.
6. Implement document + version metadata flow with signed uploads.
7. Add malware/MIME scanning gate and OCR status state machine.
8. Implement audit event writer middleware for all write paths.
9. Implement domain outbox + publisher worker + dedupe consumption primitives.
10. Implement in-app notifications + email job dispatch.
11. Add observability dashboards/alerts (API, queue, OCR, notifications, event lag).
12. Run isolation, contract, reliability, and load tests against acceptance criteria.
13. Prepare incident runbooks, rollback plan, and release gate checklist.

## 8. Open risks and unknowns with mitigation plan
- Unknown: expected Stage 0 volume per tenant and burst upload profile.
  - Mitigation: define baseline load model early; run staged load tests before Week 5 event rollout.
- Unknown: target cloud/runtime choice (affects queue and object-store primitives).
  - Mitigation: create provider-agnostic interfaces; finalize infra decision by end of Week 1.
- Unknown: enterprise SSO timeline and required protocols.
  - Mitigation: keep OIDC/SAML-ready abstraction now; defer enterprise-specific claim mapping until Stage 0.5.
- Risk: schema drift from future moat tables (`permit_reviews`, `ahj_comments`, `code_citations`, `review_outcomes`) before usage.
  - Mitigation: keep tables minimal with strict ownership boundaries; avoid premature coupling to Stage 1+ flows.

## 9. Resource list
- Internal specs:
  - `docs/stages/stage-0-foundation.md`
  - `docs/agents/shared-context.md`
  - `docs/master-prd.md`
- Official docs to consult during implementation:
  - PostgreSQL docs (RLS, indexing, partitioning, locking/concurrency).
  - Cloud provider docs for object storage security + signed URLs.
  - Queue/broker docs for retries, DLQ, redrive, and visibility timeout semantics.
  - Email provider docs for webhook delivery states and suppression handling.

## Task 2: Stage 0 Implementation Blueprint (Decision-Complete)

### 1) Final RBAC permission matrix (role x action)

Legend: `Y` = allowed, `N` = denied.

| Action | owner | admin | pm | reviewer | subcontractor |
|---|---:|---:|---:|---:|---:|
| Create organization (`POST /orgs`) | Y | N | N | N | N |
| Invite org user (`POST /orgs/{orgId}/users`) | Y | Y | N | N | N |
| Change user role | Y | Y (except `owner`) | N | N | N |
| Create project (`POST /projects`) | Y | Y | Y | N | N |
| Update project metadata | Y | Y | Y | N | N |
| Create permit | Y | Y | Y | N | N |
| Update permit status | Y | Y | Y | N | N |
| Create task (`POST /projects/{projectId}/tasks`) | Y | Y | Y | Y | N |
| Update task status (`PATCH /tasks/{taskId}`) | Y | Y | Y | Y | Y (only if assignee) |
| Reassign task (`PATCH /tasks/{taskId}` assignee) | Y | Y | Y | N | N |
| Set task due date/discipline/priority | Y | Y | Y | N | N |
| Add task comment | Y | Y | Y | Y | Y (if project member) |
| Upload document (`POST /projects/{projectId}/documents`) | Y | Y | Y | Y | Y |
| Create document version | Y | Y | Y | Y | Y |
| Edit document metadata/tags | Y | Y | Y | Y | N |
| View project timeline (`GET /projects/{projectId}/timeline`) | Y | Y | Y | Y | Y (if project member) |
| Access audit export endpoint | Y | Y | N | N | N |
| Retry notification job (ops endpoint) | Y | Y | N | N | N |

Locked defaults:
- Role scope is organization-level in Stage 0 (`memberships`), with optional `workspace_id` nullable for future overrides.
- `subcontractor` can only mutate tasks where `tasks.assignee_user_id = current_user_id`.
- No endpoint allows changing/removing `owner` except dedicated future org-transfer flow (out of Stage 0).

### 2) Exact DB migration plan (ordered)

Migration naming convention: timestamped SQL files under `db/migrations`.

1. `20260302_0001_enable_extensions.sql`
- `CREATE EXTENSION IF NOT EXISTS pgcrypto;`
- `CREATE EXTENSION IF NOT EXISTS citext;`

2. `20260302_0002_create_types.sql`
- Enums:
  - `membership_role`: `owner`, `admin`, `pm`, `reviewer`, `subcontractor`
  - `task_status`: `todo`, `in_progress`, `blocked`, `done`
  - `permit_status`: `draft`, `submitted`, `in_review`, `approved`, `rejected`, `issued`
  - `document_ocr_status`: `uploaded`, `scanning`, `queued_for_ocr`, `processing`, `completed`, `failed`
  - `notification_channel`: `in_app`, `email`
  - `notification_status`: `pending`, `processing`, `sent`, `retry`, `failed`, `dead_letter`
  - `event_status`: `pending`, `published`, `failed`, `dead_letter`

3. `20260302_0003_identity_and_tenancy.sql`
- Tables:
  - `organizations(id uuid pk, name text not null, slug citext unique not null, created_at timestamptz not null default now(), created_by uuid not null)`
  - `workspaces(id uuid pk, organization_id uuid not null fk organizations(id), name text not null, is_default boolean not null default false, created_at timestamptz not null default now(), unique(organization_id, name))`
  - `users(id uuid pk, email citext unique not null, full_name text not null, status text not null default 'active', created_at timestamptz not null default now())`
  - `user_identities(id uuid pk, user_id uuid not null fk users(id), provider text not null, provider_subject text not null, created_at timestamptz not null default now(), unique(provider, provider_subject), unique(user_id, provider))`
  - `memberships(id uuid pk, organization_id uuid not null fk organizations(id), workspace_id uuid null fk workspaces(id), user_id uuid not null fk users(id), role membership_role not null, invited_by uuid null fk users(id), created_at timestamptz not null default now(), unique(organization_id, workspace_id, user_id))`
- Constraints:
  - default workspace uniqueness: partial unique index `one_default_workspace_per_org` on `workspaces(organization_id) where is_default`.

4. `20260302_0004_core_domain.sql`
- Tables:
  - `ahj_profiles(id uuid pk, organization_id uuid not null, name text not null, jurisdiction_type text not null, region text null, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now())`
  - `projects(id uuid pk, organization_id uuid not null, workspace_id uuid not null, ahj_profile_id uuid null, name text not null, project_code text null, address jsonb not null default '{}'::jsonb, metadata jsonb not null default '{}'::jsonb, created_by uuid not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(organization_id, project_code))`
  - `project_contacts(id uuid pk, organization_id uuid not null, project_id uuid not null, name text not null, email citext null, phone text null, company text null, role text null, created_at timestamptz not null default now())`
  - `permits(id uuid pk, organization_id uuid not null, project_id uuid not null, permit_type text not null, status permit_status not null default 'draft', submitted_at timestamptz null, issued_at timestamptz null, metadata jsonb not null default '{}'::jsonb, created_by uuid not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now())`
  - `tasks(id uuid pk, organization_id uuid not null, project_id uuid not null, permit_id uuid null, title text not null, description text null, discipline text null, status task_status not null default 'todo', assignee_user_id uuid null, due_date date null, priority smallint not null default 3 check (priority between 1 and 5), created_by uuid not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), version integer not null default 1)`
  - `task_comments(id uuid pk, organization_id uuid not null, task_id uuid not null, author_user_id uuid not null, body text not null check (length(body) > 0), created_at timestamptz not null default now())`
- FKs (all `ON DELETE RESTRICT` unless noted):
  - `projects.workspace_id -> workspaces.id`
  - `projects.ahj_profile_id -> ahj_profiles.id`
  - `project_contacts.project_id -> projects.id ON DELETE CASCADE`
  - `permits.project_id -> projects.id ON DELETE CASCADE`
  - `tasks.project_id -> projects.id ON DELETE CASCADE`
  - `tasks.permit_id -> permits.id`
  - `task_comments.task_id -> tasks.id ON DELETE CASCADE`

5. `20260302_0005_documents.sql`
- Tables:
  - `documents(id uuid pk, organization_id uuid not null, project_id uuid not null, latest_version_no integer not null default 0 check (latest_version_no >= 0), title text not null, category text null, created_by uuid not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now())`
  - `document_versions(id uuid pk, organization_id uuid not null, document_id uuid not null, version_no integer not null check (version_no > 0), storage_key text not null, storage_bucket text not null, file_name text not null, file_size_bytes bigint not null check (file_size_bytes > 0), mime_type text not null, checksum_sha256 text not null, uploaded_by uuid not null, uploaded_at timestamptz not null default now(), virus_scan_status text not null default 'pending', virus_scan_completed_at timestamptz null, ocr_status document_ocr_status not null default 'uploaded', ocr_page_count integer null, ocr_error_code text null, ocr_completed_at timestamptz null, unique(document_id, version_no), unique(storage_bucket, storage_key))`
  - `document_tags(id uuid pk, organization_id uuid not null, document_id uuid not null, tag text not null, created_at timestamptz not null default now(), unique(document_id, tag))`
- Constraint trigger:
  - enforce monotonic `document_versions.version_no` and synchronize `documents.latest_version_no`.

6. `20260302_0006_events_notifications_and_moat.sql`
- Tables:
  - `audit_events(id uuid pk, organization_id uuid not null, project_id uuid null, actor_user_id uuid null, action text not null, entity_type text not null, entity_id uuid not null, occurred_at timestamptz not null default now(), request_id text not null, trace_id text null, payload jsonb not null default '{}'::jsonb, prev_hash text null, event_hash text not null, immutable boolean not null default true)`
  - `domain_events(id uuid pk, organization_id uuid not null, aggregate_type text not null, aggregate_id uuid not null, event_type text not null, event_version integer not null, idempotency_key text not null, trace_id text null, occurred_at timestamptz not null, payload jsonb not null, status event_status not null default 'pending', publish_attempts integer not null default 0, published_at timestamptz null, created_at timestamptz not null default now(), unique(organization_id, idempotency_key))`
  - `notification_jobs(id uuid pk, organization_id uuid not null, user_id uuid not null, channel notification_channel not null, template_key text not null, dedupe_key text not null, status notification_status not null default 'pending', payload jsonb not null default '{}'::jsonb, attempt_count integer not null default 0, next_attempt_at timestamptz not null default now(), provider_message_id text null, last_error text null, created_at timestamptz not null default now(), sent_at timestamptz null, unique(organization_id, dedupe_key, channel))`
  - `event_consumer_dedup(consumer_name text not null, event_id uuid not null, processed_at timestamptz not null default now(), primary key (consumer_name, event_id))`
  - Future moat tables:
    - `permit_reviews(id uuid pk, organization_id uuid not null, permit_id uuid not null, review_cycle integer not null, reviewer text null, submitted_at timestamptz null, outcome text null, created_at timestamptz not null default now())`
    - `ahj_comments(id uuid pk, organization_id uuid not null, permit_review_id uuid not null, citation_text text not null, discipline text null, severity text null, raw_source jsonb not null default '{}'::jsonb, created_at timestamptz not null default now())`
    - `code_citations(id uuid pk, organization_id uuid not null, ahj_comment_id uuid not null, code_system text not null, section text not null, excerpt text null, created_at timestamptz not null default now())`
    - `review_outcomes(id uuid pk, organization_id uuid not null, permit_review_id uuid not null, resolution_status text not null, resolved_by uuid null, resolved_at timestamptz null, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now())`

7. `20260302_0007_indexes.sql`
- Required composite indexes `(organization_id, id)` on tenant tables:
  - `workspaces`, `memberships`, `ahj_profiles`, `projects`, `project_contacts`, `permits`, `tasks`, `task_comments`, `documents`, `document_versions`, `document_tags`, `audit_events`, `domain_events`, `notification_jobs`, moat tables.
- Query-path indexes:
  - `permits(project_id, status, updated_at desc)`
  - `tasks(project_id, status, updated_at desc)`
  - `tasks(assignee_user_id, status, due_date)`
  - `task_comments(task_id, created_at desc)`
  - `document_versions(document_id, version_no desc)`
  - `audit_events(project_id, occurred_at desc, id desc)`
  - `audit_events(organization_id, occurred_at desc, id desc)`
  - `domain_events(status, created_at) where status in ('pending','failed')`
  - `notification_jobs(status, next_attempt_at) where status in ('pending','retry')`
  - `document_versions(ocr_status, uploaded_at) where ocr_status in ('queued_for_ocr','processing')`

8. `20260302_0008_rls_policies.sql`
- Enable RLS on all tenant-owned tables.
- Session variables used by API:
  - `SET app.current_user_id = '<uuid>'`
  - `SET app.current_organization_id = '<uuid>'`
- Base isolation policy (all tables):
  - `USING (organization_id = current_setting('app.current_organization_id', true)::uuid)`
  - `WITH CHECK (organization_id = current_setting('app.current_organization_id', true)::uuid)`
- Membership guard function:
  - `app_has_org_role(org_id uuid, allowed membership_role[]) returns boolean`
- Write policies:
  - `owner`/`admin` full write on org-owned tables.
  - `pm` write on `projects`, `permits`, `tasks`, `task_comments`, `documents`, `document_versions`, `document_tags`, read-only on membership/admin tables.
  - `reviewer` write on `tasks` (status + comments), `documents` upload/version create only.
  - `subcontractor` write only on `tasks` where `assignee_user_id = current_user_id` and `task_comments` for visible tasks.
- Append-only enforcement:
  - deny `UPDATE/DELETE` on `audit_events` for non-`system_admin` DB role.

9. `20260302_0009_triggers_and_functions.sql`
- `set_updated_at()` trigger on mutable tables.
- `increment_task_version()` trigger on `tasks` update.
- `write_audit_event()` trigger helper for all write endpoints (or app middleware fallback).
- `domain_outbox_insert()` helper invoked in same transaction as state mutation.

10. `20260302_0010_seed_and_policy_tests.sql`
- Seed deterministic test fixtures for two organizations and cross-tenant negative checks.
- Add SQL assertions for RLS allow/deny matrix.

### 3) API contract spec (Stage 0 endpoints)

Common headers:
- `Authorization: Bearer <token>`
- `X-Request-Id` required for all mutating endpoints.
- `Idempotency-Key` required for `POST /orgs`, `POST /projects`, `POST /projects/{projectId}/documents`, `POST /projects/{projectId}/tasks`.

Error object (all non-2xx):
```json
{
  "error": {
    "code": "forbidden",
    "message": "User does not have permission to assign this task",
    "details": {},
    "request_id": "req_123"
  }
}
```

Error codes:
- `400` `bad_request`
- `401` `unauthorized`
- `403` `forbidden`
- `404` `not_found`
- `409` `conflict`
- `412` `precondition_failed`
- `415` `unsupported_media_type`
- `422` `validation_failed`
- `429` `rate_limited`
- `500` `internal_error`

#### `POST /orgs`
Request:
```json
{
  "name": "Atlas GC",
  "slug": "atlas-gc",
  "owner_user": {
    "email": "owner@atlasgc.com",
    "full_name": "Owner Name"
  }
}
```
Success `201`:
```json
{
  "organization": {"id":"org_uuid","name":"Atlas GC","slug":"atlas-gc"},
  "default_workspace": {"id":"ws_uuid","name":"Default"},
  "owner_membership": {"id":"m_uuid","role":"owner"},
  "idempotency_replayed": false
}
```
Notes:
- Idempotent by `(organization_slug, idempotency_key)`.
- `409` if slug already exists under different idempotency key.

#### `POST /orgs/{orgId}/users`
Request:
```json
{
  "email": "pm@atlasgc.com",
  "full_name": "PM User",
  "role": "pm",
  "workspace_id": null
}
```
Success `201`:
```json
{
  "membership": {
    "id": "m_uuid",
    "organization_id": "org_uuid",
    "user_id": "user_uuid",
    "role": "pm"
  }
}
```
Errors:
- `403` if caller role not in `{owner,admin}`.
- `422` invalid role.
- `409` duplicate membership.

#### `POST /projects`
Request:
```json
{
  "organization_id": "org_uuid",
  "workspace_id": "ws_uuid",
  "name": "Warehouse Retrofit",
  "project_code": "WR-001",
  "ahj_profile": {
    "name": "City of Austin",
    "jurisdiction_type": "city",
    "region": "TX"
  },
  "address": {
    "line1": "100 Main St",
    "city": "Austin",
    "state": "TX",
    "postal_code": "78701"
  }
}
```
Success `201`:
```json
{
  "project": {
    "id":"proj_uuid",
    "organization_id":"org_uuid",
    "workspace_id":"ws_uuid",
    "name":"Warehouse Retrofit",
    "project_code":"WR-001"
  },
  "ahj_profile":{"id":"ahj_uuid","name":"City of Austin"}
}
```
Errors:
- `403` for roles outside `{owner,admin,pm}`.
- `404` workspace not in tenant.
- `409` project code duplicate in org.

#### `POST /projects/{projectId}/documents`
Request:
```json
{
  "title": "Architectural Plans",
  "category": "plans",
  "file_name": "plans-v1.pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 10485760,
  "checksum_sha256": "hexsha256",
  "storage_upload": {
    "bucket": "permits-docs",
    "key": "org_uuid/proj_uuid/doc_uuid/v1/plans-v1.pdf"
  }
}
```
Success `201`:
```json
{
  "document":{"id":"doc_uuid","project_id":"proj_uuid","latest_version_no":1},
  "version":{"id":"ver_uuid","version_no":1,"ocr_status":"uploaded","virus_scan_status":"pending"},
  "upload_status":"accepted"
}
```
Errors:
- `415` MIME not allowlisted.
- `422` checksum/file size invalid.
- `409` duplicate `(bucket,key)` or version conflict.

#### `POST /projects/{projectId}/tasks`
Request:
```json
{
  "title":"Address fire egress note 14",
  "description":"Revise plan sheet A3.1",
  "discipline":"architectural",
  "permit_id":"permit_uuid",
  "assignee_user_id":"user_uuid",
  "due_date":"2026-03-20",
  "priority":2
}
```
Success `201`:
```json
{
  "task":{
    "id":"task_uuid",
    "status":"todo",
    "assignee_user_id":"user_uuid",
    "version":1
  }
}
```
Errors:
- `403` if role not permitted.
- `404` assignee or permit outside project/org.
- `422` invalid due date or priority.

#### `PATCH /tasks/{taskId}`
Required header: `If-Match: "<version>"`
Request (partial):
```json
{
  "status":"in_progress",
  "assignee_user_id":"user_uuid",
  "due_date":"2026-03-25"
}
```
Success `200`:
```json
{
  "task":{
    "id":"task_uuid",
    "status":"in_progress",
    "assignee_user_id":"user_uuid",
    "due_date":"2026-03-25",
    "version":2,
    "updated_at":"2026-03-02T12:00:00Z"
  }
}
```
Errors:
- `412` if `If-Match` version mismatch.
- `403` if subcontractor edits non-assigned task or non-status fields.
- `422` invalid status transition (`done -> in_progress` not allowed without reopen action).

#### `GET /projects/{projectId}/timeline`
Query params:
- `cursor` optional
- `limit` default `50`, max `200`
- `event_types` optional comma-separated
- `from`/`to` optional ISO8601
Success `200`:
```json
{
  "items":[
    {
      "id":"audit_uuid",
      "occurred_at":"2026-03-02T12:00:00Z",
      "action":"task.assigned",
      "entity_type":"task",
      "entity_id":"task_uuid",
      "actor_user_id":"user_uuid",
      "payload":{}
    }
  ],
  "next_cursor":"opaque_cursor"
}
```
Errors:
- `403` when caller not project member.
- `404` project not found in org scope.

### 4) Event contract spec

Envelope (all domain events):
```json
{
  "event_id": "uuid",
  "event_type": "task.created",
  "event_version": 1,
  "organization_id": "uuid",
  "aggregate_type": "task",
  "aggregate_id": "uuid",
  "occurred_at": "2026-03-02T12:00:00Z",
  "produced_by": "task-service",
  "idempotency_key": "req_123:task.created",
  "trace_id": "trace_abc",
  "signature": "base64-hmac-sha256",
  "payload": {}
}
```

Signing and verification:
- Signature = `HMAC_SHA256(secret, canonical_json_without_signature)`.
- Consumers reject events with invalid signature (`dead_letter`) and alert.

Stage 0 payloads (locked):

1. `document.uploaded` v1
```json
{
  "document_id":"uuid",
  "project_id":"uuid",
  "uploader_id":"uuid",
  "version":1,
  "uploaded_at":"2026-03-02T12:00:00Z",
  "mime_type":"application/pdf",
  "file_size_bytes":10485760
}
```

2. `document.ocr_completed` v1
```json
{
  "document_id":"uuid",
  "version":1,
  "ocr_status":"completed",
  "page_count":42,
  "completed_at":"2026-03-02T12:05:00Z",
  "error_code":null
}
```

3. `task.created` v1
```json
{
  "task_id":"uuid",
  "project_id":"uuid",
  "permit_id":"uuid",
  "discipline":"architectural",
  "created_by":"uuid",
  "assignee_user_id":"uuid",
  "due_date":"2026-03-20"
}
```

4. `task.assigned` v1
```json
{
  "task_id":"uuid",
  "assignee_id":"uuid",
  "assigned_by":"uuid",
  "assigned_at":"2026-03-02T12:01:00Z"
}
```

5. `permit.status_changed` v1
```json
{
  "permit_id":"uuid",
  "project_id":"uuid",
  "old_status":"submitted",
  "new_status":"in_review",
  "source":"user_action",
  "changed_at":"2026-03-02T13:00:00Z",
  "changed_by":"uuid"
}
```

Idempotency handling:
- Producer writes business row + `domain_events` row in one DB transaction.
- `domain_events` unique key: `(organization_id, idempotency_key)`.
- Publisher fetches `status in ('pending','failed')` with `FOR UPDATE SKIP LOCKED`.
- Consumer stores `(consumer_name, event_id)` in `event_consumer_dedup` before side effects; duplicate insert means replay, side effect skipped.
- Retry policy: exponential backoff `1m, 5m, 15m, 1h, 6h`, then DLQ.

### 5) Test plan mapped to acceptance criteria

Acceptance criterion A: `100% pass on tenant-isolation integration tests`
- Tests:
  - A1: cross-org read denial for every Stage 0 GET path.
  - A2: cross-org write denial for every mutating endpoint.
  - A3: direct SQL policy tests for each tenant table using two org fixtures.
  - A4: negative join tests (project in org A + task in org B must fail FK/policy path).
- Pass gate: all A-tests mandatory, zero flaky retries.

Acceptance criterion B: `p95 project timeline query <= 300 ms for 10k events`
- Tests:
  - B1: seed 10k `audit_events` for one project; run 1k timeline requests with realistic filters.
  - B2: keyset pagination test for first page and deep cursor page.
  - B3: concurrency test with background writes to ensure read latency remains <= 300 ms p95.
- Pass gate: p95 <= 300 ms and p99 <= 500 ms in staging hardware profile.

Acceptance criterion C: `project -> permit -> task -> document lifecycle fully usable`
- Tests:
  - C1: happy-path integration from org creation to completed OCR document.
  - C2: role-based lifecycle tests (`pm` creates project/permit/task; `reviewer` updates task; `subcontractor` updates assigned task only).
  - C3: rollback tests for partial failures (document metadata created but upload callback missing).
- Pass gate: full lifecycle completes with no manual DB patching.

Acceptance criterion D: `every write emits audit and (where applicable) domain events`
- Tests:
  - D1: contract test asserting audit row count increments for each write endpoint.
  - D2: event snapshot tests for required event types and payload schema.
  - D3: idempotency replay tests ensure no duplicate domain events for same key.
  - D4: consumer replay test verifies dedupe table suppresses duplicate side effects.
- Pass gate: 100% endpoint coverage for audit emission; 100% required event coverage.

### 6) Week-by-week execution backlog (owners + dependencies)

Owner keys:
- `BE1` Backend lead
- `BE2` Backend engineer
- `DE` Data/platform engineer
- `SRE` Platform/SRE
- `QA` QA/automation
- `SEC` Security engineer

Week 1 (tenancy, RBAC, auth scaffolding):
- W1.1 Finalize RBAC matrix and permission engine interface (`BE1`) deps: none
- W1.2 Implement migrations `0001-0003` (`DE`) deps: W1.1
- W1.3 Auth context middleware (`current_user_id`, `current_organization_id`) (`BE2`) deps: W1.1
- W1.4 RLS base policies draft (`DE`) deps: W1.2, W1.3

Week 2 (core schema + project/permit CRUD):
- W2.1 Implement migrations `0004`, `0007` partial indexes for core entities (`DE`) deps: W1.2
- W2.2 Build `POST /projects` + permit create/update internal service (`BE1`) deps: W2.1, W1.3
- W2.3 Build `POST /orgs` and `POST /orgs/{orgId}/users` (`BE2`) deps: W1.2, W1.1
- W2.4 Audit middleware skeleton (`BE2`) deps: W2.2, W2.3

Week 3 (documents/version + storage):
- W3.1 Implement migrations `0005` (`DE`) deps: W2.1
- W3.2 Signed upload + document/version endpoint (`BE1`) deps: W3.1
- W3.3 AV + MIME validation worker path (`BE2`, `SEC`) deps: W3.2
- W3.4 OCR state machine + queue wiring (`BE2`, `SRE`) deps: W3.2

Week 4 (tasks/comments/workflow):
- W4.1 Implement task APIs (`POST /tasks`, `PATCH /tasks`) with optimistic concurrency (`BE1`) deps: W2.1
- W4.2 Task comments + assignment restrictions (`BE2`) deps: W4.1, W1.1
- W4.3 Subcontractor scoped write tests (`QA`) deps: W4.1, W4.2

Week 5 (audit + domain events):
- W5.1 Implement migrations `0006`, `0009` (`DE`) deps: W2.4, W3.4, W4.1
- W5.2 Outbox publisher + retries + DLQ (`BE2`, `SRE`) deps: W5.1
- W5.3 Event signing + verification libraries (`SEC`, `BE1`) deps: W5.1
- W5.4 Event consumer dedupe primitive + tests (`BE1`, `QA`) deps: W5.2

Week 6 (notifications + hardening + release gate):
- W6.1 Notification jobs + email provider adapter (`BE2`) deps: W5.1
- W6.2 Timeline endpoint optimization and load tests (`BE1`, `QA`) deps: W5.1
- W6.3 Complete RLS policies migration `0008` + policy regression suite `0010` (`DE`, `QA`) deps: W4.3, W5.1
- W6.4 Security review, runbooks, release checklist (`SEC`, `SRE`, `QA`) deps: W6.1, W6.2, W6.3

### 7) Top 10 implementation risks with mitigations

1. Cross-tenant data leakage through overlooked query path.
- Mitigation: mandatory repository helpers requiring `organization_id`, RLS on all tenant tables, policy CI tests for every table.

2. Role escalation via inconsistent endpoint checks.
- Mitigation: single policy engine function used by all handlers; table-driven RBAC tests generated from the matrix above.

3. Duplicate events from retries causing repeated side effects.
- Mitigation: outbox unique idempotency key + consumer dedupe PK `(consumer_name, event_id)`.

4. Lost task updates under concurrent edits.
- Mitigation: `If-Match` + row `version` optimistic concurrency; return `412` on mismatch.

5. Audit trail tampering or accidental mutation.
- Mitigation: append-only table permissions, hash-chain fields, periodic integrity verification job.

6. Document malware bypass due to race between upload and availability.
- Mitigation: keep file in quarantine state until scan pass; block downstream OCR for failed/pending scan.

7. OCR queue backlog affecting document lifecycle usability.
- Mitigation: per-org queue partition key, autoscaling workers on lag threshold, DLQ with operator replay script.

8. Timeline endpoint latency degradation past acceptance threshold.
- Mitigation: keyset pagination + dedicated composite index + capped page size + load test gate before release.

9. Notification delivery inconsistency (silent drops/bounces).
- Mitigation: provider webhook reconciliation, retry by error class, suppression list sync, dead-letter alerting.

10. Migration rollout failure in production (lock contention or long DDL).
- Mitigation: split migrations into additive steps, create indexes concurrently where possible, pre-prod dry run on production-like dataset.

## Task 3: Tenancy + Status Contract Corrections

This section supersedes conflicting snippets in Task 2 for `memberships` uniqueness and `permit_status`.

### 1) Fix `memberships` uniqueness for nullable `workspace_id`

Replace Task 2 `memberships ... unique(organization_id, workspace_id, user_id)` with:

```sql
create table memberships (
  id uuid primary key,
  organization_id uuid not null references organizations(id),
  workspace_id uuid null references workspaces(id),
  user_id uuid not null references users(id),
  role membership_role not null,
  invited_by uuid null references users(id),
  created_at timestamptz not null default now()
);

-- org-level membership uniqueness (workspace_id is null)
create unique index memberships_org_level_unique
  on memberships (organization_id, user_id)
  where workspace_id is null;

-- workspace-level membership uniqueness (workspace_id is not null)
create unique index memberships_workspace_level_unique
  on memberships (organization_id, workspace_id, user_id)
  where workspace_id is not null;
```

Additional integrity constraint (required):
```sql
alter table memberships
  add constraint memberships_workspace_belongs_to_org_chk
  check (
    workspace_id is null
    or exists (
      select 1
      from workspaces w
      where w.id = workspace_id
        and w.organization_id = memberships.organization_id
    )
  ) not valid;
```
Then backfill/validate:
```sql
alter table memberships validate constraint memberships_workspace_belongs_to_org_chk;
```

### 2) Final canonical `permit_status` enum + migration strategy

Final canonical enum (shared across Stages 0, 2, 3):
- `draft`
- `submitted`
- `in_review`
- `corrections_required`
- `approved`
- `issued`
- `expired`

Notes:
- `rejected` is removed from canonical contract and replaced by `corrections_required`.
- `expired` is included now to prevent Stage 2/3 contract churn.

Migration strategy:

If no production data yet:
```sql
drop type if exists permit_status cascade;
create type permit_status as enum (
  'draft',
  'submitted',
  'in_review',
  'corrections_required',
  'approved',
  'issued',
  'expired'
);
```

If existing data already uses prior enum (`rejected`):
```sql
create type permit_status_v2 as enum (
  'draft',
  'submitted',
  'in_review',
  'corrections_required',
  'approved',
  'issued',
  'expired'
);

alter table permits
  alter column status type permit_status_v2
  using (
    case status::text
      when 'rejected' then 'corrections_required'::permit_status_v2
      else status::text::permit_status_v2
    end
  );

drop type permit_status;
alter type permit_status_v2 rename to permit_status;
```

Add transition guard (locked):
- Allowed transitions:
  - `draft -> submitted`
  - `submitted -> in_review`
  - `in_review -> corrections_required|approved|issued|expired`
  - `corrections_required -> submitted|expired`
  - `approved -> issued|expired`
  - `issued -> expired`
  - `expired` terminal

### 3) Updated affected schema snippets and endpoint contracts

#### Updated schema snippets

`20260302_0002_create_types.sql` (`permit_status`):
```sql
create type permit_status as enum (
  'draft',
  'submitted',
  'in_review',
  'corrections_required',
  'approved',
  'issued',
  'expired'
);
```

`20260302_0003_identity_and_tenancy.sql` (`memberships` uniqueness):
- Remove table-level `unique(organization_id, workspace_id, user_id)`.
- Add the two partial unique indexes defined above.

`20260302_0004_core_domain.sql` (`permits`):
```sql
permits(
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid not null,
  permit_type text not null,
  status permit_status not null default 'draft',
  submitted_at timestamptz null,
  issued_at timestamptz null,
  expired_at timestamptz null,
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)
```

#### Updated endpoint contracts

1. `POST /projects`:
- No behavior change; clarify permit status defaults only apply when permit records are created (`draft`).

2. Permit status update endpoint (required Stage 0 contract completion):
- `PATCH /permits/{permitId}`
- Request:
```json
{
  "status": "corrections_required",
  "source": "user_action"
}
```
- Response `200` includes canonical status:
```json
{
  "permit": {
    "id": "permit_uuid",
    "status": "corrections_required",
    "updated_at": "2026-03-03T10:00:00Z"
  }
}
```
- Errors:
  - `422 validation_failed` for invalid enum value.
  - `422 validation_failed` for invalid transition.
  - `403 forbidden` for unauthorized role.

3. `PATCH /tasks/{taskId}`:
- No payload change, but any status references to permit lifecycle remain independent and unchanged.

4. `permit.status_changed` event payload:
- `old_status` and `new_status` must use canonical enum only.

### 4) Cross-stage contract alignment

Shared enums (locked for Stages 0/2/3):
- `membership_role`: `owner|admin|pm|reviewer|subcontractor`
- `task_status`: `todo|in_progress|blocked|done`
- `permit_status`: `draft|submitted|in_review|corrections_required|approved|issued|expired`
- `document_ocr_status`: `uploaded|scanning|queued_for_ocr|processing|completed|failed`

Shared event names and versions (locked):
- `document.uploaded` v1
- `document.ocr_completed` v1
- `task.created` v1
- `task.assigned` v1
- `permit.status_changed` v1

Cross-stage event envelope invariants:
- Required fields: `event_id`, `event_type`, `event_version`, `organization_id`, `aggregate_type`, `aggregate_id`, `occurred_at`, `produced_by`, `idempotency_key`, `trace_id`, `payload`.
- Idempotency key uniqueness scope: `(organization_id, idempotency_key)`.
- Signature verification required on every consumer before processing.
