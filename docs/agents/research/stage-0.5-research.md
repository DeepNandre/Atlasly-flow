# Stage 0.5 Research

Status: In Progress
Owner: Stage 0.5 agent

## 1. Stage objective recap
- Establish enterprise onboarding readiness by adding integration infrastructure, operational controls, and compliance primitives on top of Stage 0.
- Deliver reliable outbound integrations (webhooks plus connector runtime) with retries, dead-letter handling, and replayability.
- Provide portfolio KPI visibility with bounded freshness and predictable query performance.
- Implement SOC2-aligned controls for key handling, audit exports, log redaction, and privileged admin workflows.

## 2. Deep research findings

### Architecture
- Use an event-driven outbox pattern from the core domain services to integration services to avoid dual-write inconsistency between business writes and emitted integration events.
- Treat webhooks as asynchronous deliveries backed by durable `webhook_deliveries` records and an idempotency key per `(subscription_id, event_id)`.
- Use at-least-once delivery with signed payloads and explicit replay tooling; target effective exactly-once behavior for consumers through idempotency guidance.
- Standardize connector runtime lifecycle: `queued -> running -> succeeded|failed|partial`, persisted in `connector_runs`; persist record-level failures in `connector_errors`.
- Compute dashboard KPIs via incremental aggregation snapshots (`dashboard_snapshots`) with a bounded-latency refresh pipeline, not on-demand heavy joins.

### Tooling
- Queue/worker model requirements:
  - Priority queues for webhook dispatch vs connector syncs.
  - Exponential backoff + jitter for transient failures.
  - DLQ retention and replay command path with operator audit trail.
- API credentials:
  - Store only key hash and metadata in `api_credentials`.
  - One-time plaintext key reveal on creation.
  - Scoped permissions model tied to org and endpoint capabilities.
- Connector SDK:
  - Contract-first interfaces (`validateConfig`, `fetchDelta`, `mapRecord`, `emitEvents`).
  - Standardized error taxonomy (`auth`, `rate_limit`, `schema_mismatch`, `upstream_timeout`, `unknown`).
  - Built-in checkpointing (cursor/watermark) for resumable sync.

### Operations
- Observability baseline:
  - Structured logs with correlation IDs: `organization_id`, `run_id`, `delivery_id`, `event_id`.
  - Metrics for success rate, p50/p95 latency, retry count, DLQ depth, connector drift, and dashboard staleness.
  - Traces across API request -> event enqueue -> worker execution -> outcome persistence.
- Reliability operations:
  - Runbooks for webhook replay, connector auth rotation, and backup/restore validation.
  - On-call alert thresholds tied to error budgets rather than raw counts.

### Risks
- Connector instability or API shape drift can undermine trust; health scoring and provenance markers on synced records are required.
- Misconfigured webhook endpoints can flood retries; enforce per-subscription circuit breaker and temporary disablement thresholds.
- Audit/log pipelines can leak PII unless redaction is pre-ingest and centrally enforced.
- Dashboard snapshots can produce stale/incorrect analytics without strict refresh SLA and source-lag metadata.

## 3. Recommended implementation approach
1. Finalize integration contracts and schema
   - Define webhook payload versioning, HMAC signing format, retry classes, and DLQ replay semantics.
   - Define connector SDK interfaces and runtime state model.
2. Build webhook subsystem
   - Implement `POST /webhooks`, subscription validation handshake, secret generation, and scoped ownership checks.
   - Implement dispatcher worker, retry scheduler, and `webhook_deliveries` persistence.
   - Implement `GET /webhook-events` with filtering by status/date/subscription.
3. Build connector runner and SDK baseline
   - Implement runner orchestration for `POST /connectors/{name}/sync`.
   - Add checkpoint persistence, connector error taxonomy, and partial-success handling.
   - Emit `integration.run_started` and `integration.run_completed`.
4. Implement portfolio KPI pipeline
   - Define KPI formulas and dimensional model (org, project, permit status, SLA buckets).
   - Build refresh job and `GET /dashboard/portfolio`.
   - Enforce 5-minute refresh objective for 1,000 active permits via partitioned aggregate updates.
5. Ship admin/support controls
   - Org-level settings, template CRUD, API key lifecycle (`POST /orgs/{orgId}/api-keys`).
   - Restrict connector credentials and audit exports to `owner`/`admin` where specified.
6. Add SOC2-readiness controls
   - Redaction middleware for logs/events.
   - Security audit export generation (`security_audit_exports`) with access controls and immutable records.
   - Rotation policies and key custody procedures.
7. Operational hardening and reliability validation
   - SLO dashboards, synthetic webhook delivery probes, and connector canaries.
   - Quarterly backup/restore drill workflow and evidence capture.

## 4. Required APIs/data/contracts and schema guidance

### APIs
- `POST /webhooks`
  - Input: `organization_id`, `target_url`, `event_types[]`, `signing_method`, `is_active`.
  - Output: `subscription_id`, masked secret metadata, verification status.
- `GET /webhook-events`
  - Input filters: `subscription_id`, `status`, `from`, `to`, `attempt_gte`.
  - Output: paginated delivery records including final status and last error.
- `POST /connectors/{name}/sync`
  - Input: `organization_id`, optional `full_resync`, optional scope filters.
  - Output: accepted `run_id` with async status URL.
- `GET /dashboard/portfolio`
  - Output: KPI snapshot timestamp + freshness lag + core metrics.
- `POST /orgs/{orgId}/api-keys`
  - Input: `name`, `scopes[]`, `expires_at`.
  - Output: one-time key plaintext + metadata.

### Events
- `integration.run_started`
  - Required: `run_id`, `organization_id`, `connector`, `started_at`, `trigger_type`.
- `integration.run_completed`
  - Required: `run_id`, `status`, `duration_ms`, `records_synced`, `error_summary`.
- `webhook.delivery_failed`
  - Required: `subscription_id`, `event_id`, `attempt`, `error_code`, `next_retry_at`.

### Schema guidance
- `webhook_subscriptions`
  - Add unique constraint on `(organization_id, target_url, event_type_hash)` where active.
- `webhook_deliveries`
  - Add unique idempotency key on `(subscription_id, event_id, attempt)` and index `(organization_id, created_at)`.
- `connector_runs`
  - Include `started_at`, `ended_at`, `status`, `cursor`, `records_synced`, `error_count`.
- `connector_errors`
  - Store typed errors with `classification`, `external_code`, and redacted payload excerpt.
- `dashboard_snapshots`
  - Partition by day/week and maintain `snapshot_at`, `freshness_seconds`, `organization_id`.
- `api_credentials`
  - `key_hash`, `scope_json`, `last_used_at`, `rotated_at`, `revoked_at`.
- `security_audit_exports`
  - `requested_by`, `generated_at`, `time_range`, `checksum`, `storage_uri`, `access_log_ref`.

## 5. Build-vs-buy decisions and tradeoffs
- Webhook dispatcher: build in-house
  - Why: direct coupling to internal event contracts, tenant controls, and auditability needs.
- Queue/runtime: buy (managed queue) if available; otherwise build abstraction layer now
  - Why: reliability and ops burden reduction; abstraction preserves portability.
- Connector SDK/runtime: build in-house
  - Why: domain-specific mapping, provenance, and cross-connector consistency are core moat enablers.
- Secrets management: buy (managed KMS + secrets manager)
  - Why: SOC2 evidence quality, rotation primitives, and reduced cryptographic implementation risk.
- Observability stack: buy (managed metrics/log/trace)
  - Why: faster enterprise readiness and less maintenance than self-hosting from day one.

## 6. Validation and test plan
- Contract tests
  - Webhook payload schema versioning, signature verification, and replay behavior.
  - Connector SDK conformance suite for lifecycle and error taxonomy.
- Integration tests
  - Retry/backoff correctness with simulated 429/5xx and timeout failures.
  - DLQ transition and replay idempotency.
  - API key scope enforcement and revoked key rejection.
- Performance tests
  - Dashboard refresh under 1,000 active permits completes under 5 minutes.
  - Webhook dispatcher throughput sufficient for peak event bursts.
- Security/compliance tests
  - PII/secret redaction assertions in logs/events.
  - Audit export access control and tamper-evidence checksum verification.
- Chaos tests
  - Connector upstream outage simulation and recovery.
  - Queue lag injection with alerting validation.

## 7. Execution checklist
1. Confirm Stage 0 foundation exit criteria are met in production-like environment.
2. Author ADRs for webhook delivery semantics, connector SDK contract, and KPI freshness model.
3. Implement schema migrations for Stage 0.5 tables and indexes.
4. Implement webhook subscription and delivery APIs with auth/RBAC.
5. Implement dispatcher worker, retry policy, DLQ, and replay tooling.
6. Implement connector runner core with run state persistence and event emission.
7. Implement one reference connector using SDK baseline for end-to-end validation.
8. Implement portfolio KPI snapshot pipeline and dashboard API.
9. Implement org admin controls, task templates, and API key lifecycle endpoints.
10. Implement security controls: key hashing, redaction middleware, audit export pipeline.
11. Build SLO dashboards, alerts, and runbooks.
12. Run reliability, security, and load validation; fix gaps.
13. Execute enterprise readiness review and stage exit sign-off.

## 8. Open risks and unknowns with mitigation plan
- Unknown: initial connector target for Stage 0.5 exit
  - Mitigation: choose one low-complexity/high-value system and freeze scope by Week 1.
- Unknown: expected webhook event volume per org
  - Mitigation: run load model scenarios and size queue/worker concurrency before production rollout.
- Unknown: KPI definitions across customer segments
  - Mitigation: align on canonical metric dictionary and version KPI formulas.
- Risk: operational overload during first enterprise onboarding
  - Mitigation: feature flags by org, canary release, and dedicated onboarding runbooks.
- Risk: incomplete SOC2 evidence capture
  - Mitigation: map every control to owner, test artifact, and evidence storage path before launch.

## 9. Resource list
- Internal specs
  - `docs/agents/shared-context.md`
  - `docs/agents/stage-0.5-agent-prompt.md`
  - `docs/stages/stage-0.5-enterprise-readiness.md`
  - `docs/stages/stage-0-foundation.md`
  - `docs/stages/README.md`
- Internal follow-up artifacts to produce next
  - Stage 0.5 control matrix (SOC2 readiness mapped to product components).
  - Stage 0.5 SLO/alert catalog with service ownership.
  - Stage 0.5 ADR set (webhooks, connectors, KPI pipeline).

## Task 2

### 1) Webhook delivery spec (signing, retries, DLQ, replay, idempotency)

#### 1.1 Event envelope and headers
- HTTP method: `POST`
- Content-Type: `application/json`
- Canonical envelope:
  - `event_id` (UUIDv7)
  - `event_type` (string, versioned, e.g. `permit.status_changed.v1`)
  - `occurred_at` (ISO-8601 UTC)
  - `organization_id` (UUID)
  - `delivery_id` (UUID per attempt)
  - `payload` (object)
  - `schema_version` (integer)
- Required headers:
  - `X-Atlasly-Event-Id: <event_id>`
  - `X-Atlasly-Event-Type: <event_type>`
  - `X-Atlasly-Delivery-Id: <delivery_id>`
  - `X-Atlasly-Timestamp: <unix_seconds>`
  - `X-Atlasly-Signature: v1=<hex_hmac_sha256>`
  - `X-Atlasly-Attempt: <attempt_number>`

#### 1.2 Signing standard
- Algorithm: HMAC-SHA256.
- Signing secret per webhook subscription, generated at create time, stored encrypted; never returned after creation.
- Signing string format:
  - `<timestamp>.<raw_request_body>`
- Verification window:
  - Reject if timestamp skew > 300 seconds.
- Rotation:
  - Dual-secret window allowed for 24 hours (`current_secret` + `next_secret`) to support zero-downtime rotation.

#### 1.3 Delivery semantics and retries
- Delivery guarantee: at-least-once.
- Success criteria: any `2xx` response.
- Non-retry classes:
  - `400-499` except `408` and `429`.
  - Terminal failure recorded as `non_retryable_client_error`.
- Retry classes:
  - `408`, `429`, `5xx`, network timeout, TLS/connectivity failures.
- Timeout budget:
  - Connect timeout: 3s.
  - Request timeout: 10s.
- Retry schedule (exponential with jitter):
  - Attempt 1: immediate.
  - Attempt 2: +30s.
  - Attempt 3: +2m.
  - Attempt 4: +10m.
  - Attempt 5: +30m.
  - Attempt 6: +2h.
  - Attempt 7: +8h (final).
- Max attempts: 7.
- Circuit breaker:
  - Auto-disable subscription for 15 minutes when rolling 10-minute failure rate > 90% with at least 20 attempts.

#### 1.4 DLQ and replay
- DLQ entry conditions:
  - Max attempts exhausted for retryable classes.
  - Dispatcher internal processing error after local retries.
- DLQ retention: 30 days.
- Replay modes:
  - `replay_single(delivery_id)`
  - `replay_subscription(subscription_id, from, to, max_events)`
  - `replay_event(event_id)` across all affected subscriptions.
- Replay guardrails:
  - RBAC: `owner` and `admin` only.
  - Replay rate limit: 50 deliveries/min per organization.
  - All replay actions emit immutable audit event with actor, scope, and count.

#### 1.5 Idempotency model
- Producer idempotency key:
  - `delivery_key = sha256(subscription_id + ":" + event_id + ":" + attempt)`
- Database constraints:
  - Unique `(subscription_id, event_id, attempt)` on `webhook_deliveries`.
  - Unique `(subscription_id, event_id)` for final-delivered marker row.
- Consumer guidance:
  - Consumers must dedupe by `event_id`.
  - `event_id` stable across retries and replays.

### 2) Connector SDK spec (interfaces, lifecycle, error taxonomy, checkpoint model)

#### 2.1 SDK interfaces
```ts
export type ConnectorRunMode = "delta" | "full";
export type ConnectorRunStatus = "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled";

export interface ConnectorContext {
  organizationId: string;
  runId: string;
  nowIso: string;
  logger: Logger;
  emitEvent: (eventType: string, payload: Record<string, unknown>) => Promise<void>;
  redact: <T>(value: T) => T;
}

export interface ConnectorCheckpoint {
  cursor?: string;
  watermarkIso?: string;
  version: number;
}

export interface ConnectorRecord {
  externalId: string;
  updatedAtIso?: string;
  raw: Record<string, unknown>;
}

export interface NormalizedRecord {
  sourceSystem: string;
  sourceId: string;
  data: Record<string, unknown>;
  provenance: { runId: string; fetchedAtIso: string };
}

export interface ConnectorDefinition {
  name: string;
  validateConfig(config: unknown): Promise<void>;
  fetchDelta(
    config: unknown,
    checkpoint: ConnectorCheckpoint | null,
    ctx: ConnectorContext
  ): AsyncGenerator<ConnectorRecord>;
  mapRecord(record: ConnectorRecord, ctx: ConnectorContext): Promise<NormalizedRecord | null>;
  persist(records: NormalizedRecord[], ctx: ConnectorContext): Promise<{ written: number }>;
  nextCheckpoint(records: ConnectorRecord[], prev: ConnectorCheckpoint | null): ConnectorCheckpoint;
}
```

#### 2.2 Run lifecycle and state machine
- State flow:
  - `queued -> running -> succeeded`
  - `queued -> running -> partial`
  - `queued -> running -> failed`
  - `queued -> cancelled`
- Transition rules:
  - `partial`: some records persisted and at least one classified retryable/non-retryable record error.
  - `failed`: zero durable progress or fatal connector/system failure.
- Required persisted fields in `connector_runs`:
  - `run_id`, `organization_id`, `connector_name`, `mode`, `status`, `started_at`, `ended_at`, `duration_ms`,
  - `records_fetched`, `records_written`, `records_failed`, `checkpoint_before`, `checkpoint_after`, `error_summary`.

#### 2.3 Error taxonomy
- `auth.invalid_credentials`
- `auth.expired_token`
- `rate_limit.exceeded`
- `upstream.timeout`
- `upstream.unavailable`
- `schema.mismatch`
- `data.validation_failed`
- `permission.denied`
- `internal.transient`
- `internal.fatal`

Classification policy:
- Retryable:
  - `rate_limit.exceeded`, `upstream.timeout`, `upstream.unavailable`, `internal.transient`.
- Non-retryable:
  - `auth.invalid_credentials`, `permission.denied`, `schema.mismatch`, `data.validation_failed`, `internal.fatal`.
- Conditional retry:
  - `auth.expired_token` if token refresh succeeds; else non-retryable.

#### 2.4 Checkpoint model
- Checkpoint storage: one checkpoint per `(organization_id, connector_name)`.
- Canonical fields:
  - `cursor` (opaque upstream token)
  - `watermarkIso` (last processed update time)
  - `version` (schema version for checkpoint format)
  - `updated_at`
- Commit strategy:
  - Commit checkpoint only after batch persistence success.
  - Batch size: 200 records default.
  - On partial run, commit last successful batch checkpoint.
- Full resync:
  - Requires explicit `full_resync=true`; preserves previous checkpoint in `checkpoint_history`.

### 3) SOC2 control matrix mapped to product components and evidence artifacts

| Control ID | Objective | Product component(s) | Implementation standard | Evidence artifact(s) | Owner | Cadence |
|---|---|---|---|---|---|---|
| CC6.1 | Logical access restriction | RBAC middleware, org/admin APIs | Enforce role checks on all mutating endpoints; deny by default | RBAC integration test results, access policy doc, sampled audit logs | App Eng | Per release |
| CC6.2 | Privileged access control | Connector credentials, audit export endpoints | Restrict to `owner/admin`; step-up auth for credential changes | Privileged action audit trail, role membership export | Security + App Eng | Weekly review |
| CC6.6 | Credential security | `api_credentials`, webhook secrets | Hash API keys at rest, encrypt webhook secrets, one-time display only | DB schema, key creation logs, secret rotation logs | Security Eng | Continuous + monthly audit |
| CC7.2 | Change monitoring | Connector runtime, webhook dispatcher | Emit structured logs/metrics for failures and drift | Dashboard screenshots, alert history, incident tickets | SRE | Continuous |
| CC7.3 | Incident response | On-call + runbooks | Pager escalation for SLO breaches; documented runbooks used in incidents | Incident postmortems, paging logs, runbook links | SRE + Incident Cmdr | Per incident |
| CC8.1 | Change management | Migrations, integration contracts | PR review + CI checks + staged rollout with feature flags | PR records, CI artifacts, release checklist | Eng Manager | Per change |
| A1.2 | Availability commitments | Webhooks, connectors, dashboard refresh jobs | Defined SLIs/SLOs with error budgets and alerting | SLO reports, error budget burn reports | SRE | Daily |
| PI1.1 | Processing integrity | KPI snapshots, connector checkpoints | Deterministic KPI formulas and checkpointed syncs with replayability | KPI definition spec, reconciliation reports | Data Eng | Weekly |
| C1.1 | Confidentiality | Log pipeline, audit exports | Redact PII/secrets before persistence/export | Redaction unit tests, log sampling evidence | Security Eng | Per release + monthly |
| CC9.2 | Backup/restore | DB + object storage + queue configs | Quarterly restore drill and documented RTO/RPO results | Drill report, restore timestamps, validation checklist | SRE + DBA | Quarterly |

Evidence storage standard:
- Store evidence under controlled bucket path:
  - `compliance-evidence/stage-0.5/<control_id>/<yyyy-mm-dd>/`
- Every artifact requires checksum, owner, and retention tag.

### 4) SLO/SLI catalog with alert thresholds and on-call runbooks

#### 4.1 SLI/SLO catalog
| Service | SLI definition | SLO target | Window | Alert threshold |
|---|---|---|---|---|
| Webhook delivery | `successful_deliveries / total_deliveries_excluding_4xx` | `>=99.0%` | Rolling 24h | Page at `<98.0%` for 15m; ticket at `<99.0%` for 1h |
| Webhook latency | p95 dispatch latency (enqueue to terminal state for successful deliveries) | `<=120s` | Rolling 1h | Page if `>300s` for 15m |
| Connector success | `successful_or_partial_runs / total_runs` | `>=98.5%` | Rolling 24h | Page at `<95%` for 30m |
| Connector freshness | Max staleness per org/connector (`now - last_successful_run_end`) | `<=60m` | Continuous | Page if `>120m`; ticket if `>60m` |
| Dashboard freshness | `now - snapshot_at` | `<=5m` for active orgs | Continuous | Page if `>15m` for 15m |
| API key abuse detection | unauthorized key attempts per org | `0 sustained anomalies` | Rolling 1h | Page on spike `>20` failed auths in 10m |

#### 4.2 On-call runbooks
- Runbook `RB-WEBHOOK-001` (delivery degradation):
  - Validate queue depth and worker health.
  - Check external endpoint error distribution by subscription.
  - Pause affected subscriptions when endpoint-side outage confirmed.
  - Replay failed deliveries after recovery.
- Runbook `RB-CONNECTOR-001` (connector drift/stale):
  - Identify failing connector and error class.
  - If auth-related, rotate credentials and trigger manual sync.
  - If schema mismatch, quarantine connector version and roll back mapping.
- Runbook `RB-DASHBOARD-001` (snapshot staleness):
  - Inspect aggregation job lag and lock contention.
  - Trigger backfill for impacted org partitions.
  - Validate KPI reconciliation sample before clearing incident.
- Runbook `RB-SECURITY-001` (key misuse):
  - Revoke suspect key immediately.
  - Rotate related secrets.
  - Collect audit evidence and open security incident ticket.

Escalation policy:
- P1 pages primary on-call immediately.
- Escalate to secondary after 10 minutes.
- Escalate to engineering manager after 20 minutes unresolved.

### 5) Dashboard KPI definitions and freshness pipeline design

#### 5.1 KPI definitions (organization-level)
- `permits_total`:
  - Count of active permits (`status != expired`).
- `permit_cycle_time_p50_days`:
  - Median days from `submitted_at` to latest of `approved_at|issued_at`.
- `permit_cycle_time_p90_days`:
  - 90th percentile same definition as above.
- `corrections_rate`:
  - `permits_with_status_corrections_required / permits_submitted_in_window`.
- `approval_rate_30d`:
  - `permits_approved_or_issued_last_30d / permits_submitted_last_30d`.
- `task_sla_breach_rate`:
  - `tasks_overdue / tasks_due_in_window`.
- `connector_health_score`:
  - Weighted score: 50% run success, 30% freshness, 20% latency (0-100).
- `webhook_delivery_success_rate`:
  - As defined in SLI table.

#### 5.2 Freshness pipeline design
- Data flow:
  - Domain events -> aggregation queue -> incremental updater -> `dashboard_snapshots`.
- Update strategy:
  - Incremental every 60 seconds for orgs with active events.
  - Full reconciliation every 6 hours.
- Partitioning:
  - Snapshot table partition by `snapshot_date` and `organization_id` hash.
- Freshness fields:
  - `snapshot_at`, `source_max_event_at`, `freshness_seconds`, `is_backfill`.
- Correctness controls:
  - Reconciliation job compares snapshots vs canonical raw tables for 1% org sample/hour.
  - If delta > 0.5% on any KPI, mark snapshot stale and trigger rebuild.

### 6) API key lifecycle policy (creation, scope, rotation, revocation)

#### 6.1 Creation
- Endpoint: `POST /orgs/{orgId}/api-keys`.
- RBAC: `owner` and `admin`.
- Required attributes:
  - `name`, `scopes[]`, `expires_at` (max 365 days), optional `ip_allowlist[]`.
- Response:
  - One-time plaintext key, `key_id`, `created_at`, `expires_at`.
- Storage:
  - Persist `key_hash` using Argon2id; never persist plaintext.

#### 6.2 Scope model
- Allowed scopes:
  - `webhooks:read`, `webhooks:write`
  - `connectors:read`, `connectors:run`
  - `dashboard:read`
  - `tasks:read`, `tasks:write`
  - `audit:read` (admin only)
- Policy:
  - Least privilege by default.
  - Scope escalation requires new key issuance; in-place escalation disallowed.

#### 6.3 Rotation
- Mandatory rotation:
  - Every 90 days for privileged scopes (`*:write`, `audit:read`).
  - Every 180 days for read-only scopes.
- Pre-expiry notifications:
  - T-14 days, T-7 days, T-1 day.
- Grace window:
  - Optional overlap max 24 hours with old/new key both valid.

#### 6.4 Revocation
- Immediate revocation triggers:
  - Suspected compromise, owner/admin manual action, inactivity > 120 days, role downgrade.
- Revocation behavior:
  - Set `revoked_at` and deny all subsequent authentication immediately.
  - Emit audit event `api_key.revoked`.
- Post-revocation:
  - Require replacement key and integration health check.

#### 6.5 Monitoring and evidence
- Metrics:
  - key creation count, active keys, nearing expiry, failed auth by key_id, revoked key usage attempts.
- Evidence:
  - Monthly key inventory report per organization.
  - Rotation compliance report and exception register.

### 7) Implementation backlog with sequencing and hard gates

#### 7.1 Sequenced backlog
1. `EPIC-05-01` Contracts and ADRs
   - Finalize webhook envelope/signing spec, SDK interface spec, KPI dictionary.
2. `EPIC-05-02` Data model and migrations
   - Create Stage 0.5 tables and constraints; add indexes and partition config.
3. `EPIC-05-03` Webhook control plane
   - Build subscription APIs, secret generation, verification handshake.
4. `EPIC-05-04` Webhook dispatch plane
   - Implement queue workers, retries, DLQ, replay APIs/ops commands.
5. `EPIC-05-05` Connector runtime + SDK
   - Implement runner service, checkpoint store, taxonomy-based error handling.
6. `EPIC-05-06` Reference connector
   - Ship one production-grade connector using SDK and runbook coverage.
7. `EPIC-05-07` KPI pipeline + dashboard API
   - Incremental aggregation, snapshot reconciliation, freshness signals.
8. `EPIC-05-08` API key lifecycle controls
   - Scoped key creation, hash storage, rotation and revocation workflows.
9. `EPIC-05-09` SOC2 control instrumentation
   - Redaction middleware, audit export pipeline, evidence storage conventions.
10. `EPIC-05-10` SRE readiness
   - SLO dashboards, alerts, runbooks, incident exercises, restore drill.
11. `EPIC-05-11` Reliability and compliance exit validation
   - Load/chaos/security tests and formal stage sign-off.

#### 7.2 Hard gates
- Gate A (before `EPIC-05-02`):
  - Stage 0 tenant isolation tests passing and event bus stable.
- Gate B (before `EPIC-05-04` production enablement):
  - Signature verification integration tests passing and replay audit trail validated.
- Gate C (before `EPIC-05-06`):
  - Connector SDK conformance suite green.
- Gate D (before `EPIC-05-07` launch):
  - KPI definitions approved by product/data stakeholders.
- Gate E (before enterprise onboarding):
  - All P1/P2 SLO alerts wired to on-call, runbooks reviewed, first backup/restore drill complete.
- Gate F (stage exit):
  - Webhook success SLO met for 7 consecutive days.
  - Dashboard freshness SLO met for 7 consecutive days.
  - One external system live on webhook stream.
  - SOC2 control evidence package complete for mapped controls.

## Task 3

### Canonical contract registry draft (all stages)

#### 1) Source-of-truth registry tables

##### 1.1 Shared enums registry
| Enum | Allowed values | Notes |
|---|---|---|
| `permit_status` | `submitted`, `in_review`, `corrections_required`, `approved`, `issued`, `expired` | Canonical stage-wide status set from stage roadmap shared terminology. |
| `task_status` | `todo`, `in_progress`, `blocked`, `done` | Stage 0 workflow state set. |
| `connector_run_status` | `queued`, `running`, `succeeded`, `partial`, `failed`, `cancelled` | Stage 0.5 connector runtime state machine. |
| `webhook_delivery_status` | `pending`, `retrying`, `delivered`, `failed_retryable`, `failed_non_retryable`, `dead_lettered` | Delivery lifecycle and DLQ terminal states. |
| `audit_actor_type` | `user`, `system`, `service` | For immutable audit timeline and export consistency. |

##### 1.2 Shared event names registry
| Event name | Producer | Required domain fields (in `payload`) |
|---|---|---|
| `document.uploaded` | document service | `document_id`, `project_id`, `uploader_id`, `version`, `uploaded_at` |
| `document.ocr_completed` | document processing worker | `document_id`, `ocr_status`, `page_count`, `completed_at` |
| `task.created` | task service | `task_id`, `project_id`, `discipline`, `created_by` |
| `task.assigned` | task service | `task_id`, `assignee_id`, `assigned_by`, `assigned_at` |
| `permit.status_changed` | permit service | `permit_id`, `old_status`, `new_status`, `source`, `changed_at` |
| `integration.run_started` | integration service | `connector`, `organization_id`, `run_id`, `started_at` |
| `integration.run_completed` | integration service | `run_id`, `status`, `duration_ms`, `records_synced` |
| `webhook.delivery_failed` | webhook dispatcher | `subscription_id`, `event_id`, `attempt`, `error_code` |
| `api_key.revoked` | auth/admin service | `organization_id`, `key_id`, `revoked_by`, `revoked_at`, `reason` |

Naming rules:
- Format: `<bounded_context>.<entity_or_flow>.<action>` in lowercase snake segments separated by dots.
- Event names are immutable once published.
- New semantics require a new event name and/or schema version.

##### 1.3 Required event envelope fields (all events)
| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | UUIDv7 string | Yes | Stable per logical event, used for dedupe and tracing. |
| `event_name` | string | Yes | Must exist in shared event names registry. |
| `event_version` | integer | Yes | Starts at `1`; increments on schema change. |
| `occurred_at` | ISO-8601 UTC string | Yes | Domain occurrence timestamp. |
| `published_at` | ISO-8601 UTC string | Yes | Time pushed to bus/webhook dispatcher. |
| `organization_id` | UUID string | Yes | Tenant boundary and routing key. |
| `producer` | string | Yes | Service identifier (e.g., `permit-service`). |
| `trace_id` | string | Yes | Cross-service observability correlation id. |
| `idempotency_key` | string | Yes | Deterministic key per event contract rules. |
| `payload` | object | Yes | Domain-specific body for the event. |
| `schema_ref` | string | Yes | Pointer to schema doc or schema id (e.g., `contracts/permit.status_changed/v1`). |

Envelope invariants:
- `organization_id` must match payload tenant ownership.
- `event_id` must remain unchanged across retries/replays.
- `event_name` + `event_version` must map to one unique schema.

#### 2) Versioning policy and compatibility rules

##### 2.1 Versioning policy
- Apply semantic rules to each contract type:
  - Event schema: integer `event_version`.
  - Enum registry: integer `enum_version`.
  - Envelope spec: integer `envelope_version`.
- Default evolution rule: additive-only.
  - Allowed: add optional payload fields, add new event names, add enum values only when explicitly permitted.
  - Not allowed without new major/version bump: remove field, rename field, change type/meaning, tighten optional->required.

##### 2.2 Compatibility rules
- Producers:
  - Must emit all currently required fields for declared version.
  - Must not reuse existing event names for breaking semantic changes.
- Consumers:
  - Must ignore unknown fields.
  - Must tolerate event ordering variance and duplicate deliveries.
- Enums:
  - `permit_status` is closed set unless registry version explicitly updates with migration note.
  - Unknown enum values must be treated as non-terminal and logged with warning, not hard-failed at parser boundary.

##### 2.3 Deprecation window and lifecycle
- Minimum deprecation window for any contract version: 90 days.
- Required timeline:
  - Day 0: mark version deprecated in registry with replacement target.
  - Day 30: publish migration guide and rollout tracker.
  - Day 60: enforce warning alerts for lagging consumers.
  - Day 90: eligible for removal if zero active consumers.
- Removal gate:
  - Contract owner + platform owner sign-off.
  - Evidence: consumer adoption report and compatibility test pass.

##### 2.4 Required migration notes
Every contract change PR must include:
- Change classification (`additive`, `deprecation`, `breaking`).
- Affected producers and consumers.
- Data backfill or replay requirements.
- Rollout plan (feature flag/canary/full rollout dates).
- Rollback plan and blast-radius estimate.
- Test evidence links (contract tests + integration tests).

#### 3) CI validation checks for stage docs

CI should run a `contracts-lint` job against `docs/stages/*.md` and registry references.

##### 3.1 Required checks
- Registry reference check:
  - Every stage doc event and enum reference must match a canonical registry entry.
- Enum value check:
  - `permit_status` values in any stage doc must be a subset of canonical set.
- Envelope field check:
  - Any described event contract must include all required envelope fields or explicitly reference shared envelope spec.
- Naming convention check:
  - Event names must match regex `^[a-z]+(\.[a-z_]+){2,}$`.
- Schema evolution rule check:
  - Contract diffs are additive-only unless PR includes approved breaking-change metadata.
- Deprecation policy check:
  - Deprecated contracts must include deprecation date, replacement, and removal target date.
- Migration note check:
  - Any contract change in stage docs requires a “Migration Notes” block with required fields.
- Stage consistency check:
  - Stage docs must not redefine canonical enums/events with conflicting values.

##### 3.2 Recommended CI outputs
- Block merge on failed registry checks.
- Emit machine-readable report artifact:
  - `artifacts/contracts-lint-report.json`
- Emit human-readable summary:
  - missing registry entries
  - invalid enum values
  - envelope field omissions
  - missing migration notes

##### 3.3 Ownership and enforcement
- Registry owners: Platform Architecture + Integration lead.
- Required reviewers on contract changes: one platform owner and one consuming service owner.
- SLA for registry update reviews: 2 business days.
