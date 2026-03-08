# Stage 1B Research

Status: In Progress
Owner: Stage 1B agent
Last Updated: 2026-03-02

## 1) Stage Objective Recap
- Convert approved Stage 1A extraction records into deterministic `tasks` with one-click execution.
- Auto-route each task via rules keyed by discipline, project role, and trade partner mapping.
- Reduce manual triage with SLA timers, escalation workflows, and targeted assignment notifications.
- Capture reassignment feedback to improve rule quality while preserving auditability and idempotency.

## 2) Deep Research Findings
### Architecture
- Use an event-driven write path: `POST /comment-letters/{letterId}/create-tasks` writes tasks and emits `tasks.bulk_created_from_extractions`; routing service consumes and emits `task.auto_assigned`.
- Enforce idempotency at generation boundary with unique key `{letter_id}:{comment_id}` (or extraction record id) and database uniqueness constraints to make retries safe.
- Separate deterministic rule evaluation from side effects:
  - evaluator: pure function returning candidate assignee + rule/confidence.
  - executor: persists assignment and dispatches notifications.
- Add a dead-letter/manual-review queue for unresolved assignments below confidence threshold.

### Tooling
- Rules storage: `routing_rules` with normalized condition fields and explicit priority/weight ordering.
- Rule simulation endpoint/tool should evaluate current rules against historical tasks before activation.
- Scheduler (cron/queue worker) for SLA reminders/escalations based on assignment acknowledgment timestamps.
- Event bus contracts should be versioned (`v1`) and include trace ids for cross-service observability.

### Operations
- Require audit trails for rule changes, assignment decisions, manual reassignments, and escalations.
- Notification fatigue controls:
  - per-user suppression windows.
  - digest mode for low urgency events.
  - escalation-only immediate alerts.
- Pilot readiness depends on instrumentation for:
  - auto-assignment hit rate.
  - time-to-first-assignee.
  - override reason distribution.

### Risks
- Discipline ambiguity leads to incorrect owners.
  - Mitigation: confidence threshold + fallback queue + required override reason taxonomy.
- Duplicate task creation under retries/race conditions.
  - Mitigation: idempotency key + unique index + transactional outbox.
- Rule sprawl and conflicting conditions.
  - Mitigation: deterministic precedence, conflict checker, simulation gating before publish.

## 3) Recommended Implementation Approach (Step-by-Step)
1. Implement schema updates (`routing_rules`, `task_assignment_feedback`, `assignment_escalations`, plus `tasks` assignment metadata).
2. Build deterministic task generation endpoint with idempotency validation and bulk-create transaction.
3. Emit `tasks.bulk_created_from_extractions` via outbox pattern.
4. Implement routing evaluator with precedence model:
   - project-specific active rules > org defaults.
   - exact discipline + trade match > discipline-only > role fallback.
   - explicit priority, then newest active rule as final tiebreak.
5. Persist auto-assignment with `rule_id`, `assignment_confidence`, and `auto_assigned=true`; emit `task.auto_assigned`.
6. Add reassignment API path to capture feedback (`from_assignee`, `to_assignee`, `reason`, `rule_miss_type`).
7. Implement SLA scheduler for acknowledgment deadlines and escalation chain (`task.assignment_overdue`).
8. Ship routing simulation UI/API for preflight checks before enabling/editing rules.
9. Instrument KPIs and run a pilot hardening cycle against acceptance criteria.

## 4) Required APIs, Data Contracts, and Schema Guidance
- `POST /comment-letters/{letterId}/create-tasks`
  - Input: optional idempotency header/key.
  - Output: `{ created_count, task_ids, idempotency_key }`.
- `POST /routing-rules` + `GET /routing-rules`
  - Support drafts and `is_active` toggling after simulation pass.
- `POST /tasks/{taskId}/reassign`
  - Must require feedback payload for learning loop.
- Event payload minimums:
  - `tasks.bulk_created_from_extractions`: `event_id`, `letter_id`, `task_ids`, `created_count`, `trace_id`, `occurred_at`.
  - `task.auto_assigned`: `task_id`, `assignee_id`, `rule_id`, `confidence`, `trace_id`.
  - `task.assignment_overdue`: `task_id`, `assignee_id`, `overdue_by_hours`, `escalation_level`.

## 5) Build-vs-Buy Decisions and Tradeoffs
- Build routing engine in-house:
  - Pros: domain-specific discipline logic, auditable precedence, easier feedback-loop tuning.
  - Cons: more implementation/maintenance burden.
- Buy/Reuse notification provider + queue infra:
  - Pros: faster delivery, proven delivery guarantees.
  - Cons: provider lock-in and adapter complexity.
- Build lightweight simulation tool in-house:
  - Pros: directly aligned to custom rule schema.
  - Cons: added UI and test surface.

## 6) Validation and Test Plan
- Unit tests:
  - rule precedence/conflict resolution.
  - confidence threshold behavior.
  - idempotent generation under duplicate requests.
- Integration tests:
  - approved extraction -> task creation -> auto-assignment -> notification flow.
  - reassignment feedback persistence + KPI counters.
- Reliability tests:
  - retry storms and duplicated event delivery.
  - scheduler drift and escalation correctness.
- Pilot analytics checks:
  - auto-assignment success >= 80%.
  - median approval-to-assigned <= 10 minutes.

## 7) Execution Checklist (Ordered, Dependency-Aware)
1. Confirm Stage 1A approval record schema and stable extraction identifiers.
2. Apply DB migrations + indexes + constraints.
3. Implement deterministic create-tasks API and outbox emission.
4. Implement routing evaluator/executor with precedence model.
5. Add reassignment feedback capture and audit logs.
6. Implement escalation/reminder scheduler and suppression policy.
7. Add routing simulation API/tooling and activation guardrails.
8. Add metrics dashboards + alerts for pilot KPIs.
9. Run pilot, collect override insights, tune rules and thresholds.

## 8) Open Risks and Unknowns with Mitigation Plan
- Unknown: final discipline taxonomy and normalization source of truth.
  - Mitigation: define canonical enum mapping and version it.
- Unknown: how confidence is calculated (heuristic vs probabilistic).
  - Mitigation: launch with deterministic heuristic scoring and log features for later ML.
- Unknown: escalation policy variance per customer org.
  - Mitigation: org-level policy templates with safe defaults and admin override.
- Unknown: acceptable notification volume per role.
  - Mitigation: start with conservative digests + observability on alert opens/clicks.

## 9) Resource List
- Internal: `docs/agents/shared-context.md`
- Internal: `docs/agents/stage-1b-agent-prompt.md`
- Internal: `docs/stages/stage-1b-ticketing-routing.md`
- Internal: `docs/stages/stage-1a-comment-extraction.md`
- Internal: `docs/stages/stage-0-foundation.md`

## Task 2

### 1) Routing rule schema and precedence algorithm (deterministic pseudocode)
#### `routing_rules` schema lock
- `id` (uuid, pk)
- `organization_id` (uuid, not null)
- `project_id` (uuid, nullable; null means org default rule)
- `is_active` (bool, not null, default false)
- `priority` (int, not null; lower number = higher precedence)
- `discipline` (text, nullable; normalized enum value)
- `project_role` (text, nullable)
- `trade_partner_id` (uuid, nullable)
- `ahj_id` (uuid, nullable)
- `assignee_user_id` (uuid, nullable)
- `assignee_team_id` (uuid, nullable)
- `confidence_base` (numeric(5,4), not null, default 0.7000)
- `effective_from` (timestamptz, not null, default now())
- `effective_to` (timestamptz, nullable)
- `created_at`, `updated_at`, `created_by`, `updated_by`
- `version` (int, not null, default 1)
- `rule_hash` (text, not null; stable hash of all match fields + target)

Indexes/constraints:
- `idx_routing_rules_lookup` on `(organization_id, project_id, discipline, is_active, effective_from)`
- unique partial: `(organization_id, project_id, priority, rule_hash)` where `is_active = true`
- check: exactly one of `assignee_user_id` or `assignee_team_id` must be non-null

Deterministic precedence (highest to lowest):
1. Active + currently effective rules only.
2. Scope specificity: project rule beats org default.
3. Match specificity score:
   - +8 discipline exact
   - +4 trade partner exact
   - +2 project role exact
   - +1 ahj exact
4. Lowest `priority` value.
5. Highest `confidence_base`.
6. Oldest `created_at` (stable tie-breaker).
7. Lowest UUID lexical order (final deterministic guard).

```text
function select_assignee(task_ctx, rules):
  candidates = []
  for rule in rules:
    if !rule.is_active: continue
    if now < rule.effective_from or (rule.effective_to != null and now >= rule.effective_to): continue
    if rule.organization_id != task_ctx.organization_id: continue
    if rule.project_id != null and rule.project_id != task_ctx.project_id: continue
    if rule.discipline != null and rule.discipline != task_ctx.discipline: continue
    if rule.trade_partner_id != null and rule.trade_partner_id != task_ctx.trade_partner_id: continue
    if rule.project_role != null and rule.project_role != task_ctx.project_role: continue
    if rule.ahj_id != null and rule.ahj_id != task_ctx.ahj_id: continue

    specificity = 0
    if rule.discipline != null: specificity += 8
    if rule.trade_partner_id != null: specificity += 4
    if rule.project_role != null: specificity += 2
    if rule.ahj_id != null: specificity += 1
    scope_rank = (rule.project_id != null) ? 0 : 1
    candidates.append((rule, scope_rank, -specificity, rule.priority, -rule.confidence_base, rule.created_at, rule.id))

  if candidates.empty():
    return {status: "MANUAL_QUEUE", confidence: 0.0, reason: "NO_MATCH"}

  sort candidates by tuple asc
  winner = candidates[0].rule
  confidence = compute_confidence(task_ctx, winner)  // deterministic formula

  if confidence < CONFIDENCE_THRESHOLD:
    return {status: "MANUAL_QUEUE", confidence: confidence, rule_id: winner.id, reason: "LOW_CONFIDENCE"}

  return {status: "ASSIGNED", assignee: winner.target, confidence: confidence, rule_id: winner.id}
```

Conflict-resolution lock:
- Conflicts are resolved by tuple ordering above only; no non-deterministic fallbacks.
- Rule publish path must run a conflict checker; if two active rules can both match with same ordering tuple except id, block publish and require priority change.

### 2) Idempotent task-generation contract from approved extractions
Endpoint:
- `POST /comment-letters/{letterId}/create-tasks`

Preconditions:
- Letter exists and belongs to caller org/project.
- Extraction records are in `APPROVED` state.

Request contract:
- Header: `Idempotency-Key` (optional, client-provided).
- Body (optional): `{ "approved_extraction_ids": [uuid...], "dry_run": false }`.

Server idempotency lock:
- Canonical key per extraction row: `gen:{organization_id}:{project_id}:{letter_id}:{extraction_id}`
- Unique constraint on `tasks(source_extraction_id)` and on `task_generation_runs(idempotency_key)`.
- If header absent, server derives deterministic run key from sorted extraction ids and letter version hash.

Execution semantics:
- Single DB transaction:
  1. Insert `task_generation_runs` row (`IN_PROGRESS`) with idempotency key.
  2. For each approved extraction: `INSERT ... ON CONFLICT (source_extraction_id) DO NOTHING`.
  3. Collect created/existing task ids.
  4. Write outbox event `tasks.bulk_created_from_extractions`.
  5. Mark run `COMPLETED` with counts.
- Retry with same key returns prior response payload (`200` idempotent replay).
- Partial failures are prevented by transaction rollback; no half-created run state.

Response:
- `{ "letter_id": "...", "created_count": n, "existing_count": m, "task_ids": [...], "idempotency_key": "...", "run_status": "COMPLETED" }`

### 3) Reassignment feedback taxonomy and learning loop data model
`task_assignment_feedback` model:
- `id`, `organization_id`, `project_id`, `task_id`
- `from_assignee_id`, `to_assignee_id`
- `source_rule_id` (nullable)
- `source_confidence` (numeric(5,4))
- `feedback_reason_code` (enum)
- `feedback_subreason` (text nullable)
- `actor_user_id`
- `was_auto_assigned` (bool)
- `created_at`
- `feature_snapshot` (jsonb: discipline, trade partner, role, ahj, schedule phase)

Taxonomy lock (`feedback_reason_code`):
- `WRONG_DISCIPLINE`
- `WRONG_TRADE_PARTNER`
- `WRONG_PROJECT_ROLE`
- `ASSIGNEE_UNAVAILABLE`
- `MISSING_RULE`
- `RULE_PRIORITY_ISSUE`
- `TEMP_CAPACITY_REDIRECT`
- `OTHER_VERIFIED`

Learning loop:
1. Every manual reassignment must include `feedback_reason_code`.
2. Nightly job aggregates drift metrics by rule and reason code.
3. Auto-create `routing_rule_suggestions` when thresholds trip:
   - `MISSING_RULE` >= 5 in 7 days per discipline/project.
   - Override rate for a rule > 20% over last 50 assignments.
4. PM/admin accepts/rejects suggestion; accepted suggestion increments rule `version`.

### 4) SLA/escalation policy model (timers, levels, suppression rules)
`assignment_escalations` model:
- `id`, `organization_id`, `project_id`, `task_id`, `policy_id`
- `current_level` (int)
- `assigned_at`, `ack_due_at`, `next_escalation_at`
- `last_notified_at`, `resolved_at`
- `status` (`OPEN|ACKNOWLEDGED|ESCALATED|RESOLVED|CANCELLED`)

Policy object (`routing_sla_policies`):
- `ack_minutes_l1` (default 120)
- `ack_minutes_l2` (default 240)
- `ack_minutes_l3` (default 480)
- `business_hours_only` (bool)
- `suppression_windows` (jsonb list)
- `max_levels` (default 3)
- `escalate_to`: l1 manager, l2 project manager, l3 org admin

Timer behavior:
- L1 starts at assignment create.
- If assignee acknowledges before `ack_due_at`, status -> `ACKNOWLEDGED`, timers stop.
- If missed, emit `task.assignment_overdue`, escalate level, compute next due.
- Stop at `max_levels`; keep daily digest reminders only.

Suppression rules:
- No duplicate immediate alerts within 30 minutes for same task + level.
- Quiet hours defer non-critical alerts; escalations still queue and flush at quiet-window end unless severity = critical.
- Digests suppress immediate reminders for non-overdue items.

### 5) Notification policy (immediate vs digest vs escalation-only)
Policy matrix:
- Immediate:
  - new auto-assignment (first assignment only)
  - direct reassignment to a user
  - escalation level change
- Digest:
  - upcoming SLA due within 60 minutes
  - low-confidence assignments sent to manual queue
  - rule-change informational updates
- Escalation-only:
  - users can opt out of routine immediate alerts but cannot opt out of escalation notices for owned tasks.

Delivery controls:
- Channel order: in-app -> email -> connector webhook (if configured).
- De-dup key: `{task_id}:{event_type}:{level}:{assignee_id}`.
- User preferences are bounded by org minimum policy (enterprise control).

### 6) Pilot KPI instrumentation and dashboard definitions
Event instrumentation:
- `task_generation.requested|completed|replayed`
- `routing.evaluated|assigned|manual_queue`
- `task.reassigned`
- `sla.level_breached`
- `notification.sent|suppressed|digest_batched`

Dashboard A: Routing Quality
- Auto-assignment success rate = auto-assigned tasks not manually reassigned within 24h / total auto-assigned.
- Override rate by rule.
- Top feedback reason codes.
- Low-confidence queue volume.

Dashboard B: Triage Velocity
- P50/P90 letter approval -> first assignment.
- P50/P90 letter approval -> fully assigned all tasks.
- Backlog aging of unassigned tasks.

Dashboard C: Operability
- Idempotency replay count and replay ratio.
- Duplicate-prevented inserts (`ON CONFLICT` hits).
- Scheduler lag and overdue breach counts by level.
- Notification suppression vs delivery ratio.

Pilot SLOs:
- Auto-assignment success >= 80%.
- Median approval-to-fully-assigned <= 10 minutes.
- Duplicate task creation rate = 0 (hard invariant).

### 7) Implementation backlog and cut-over plan from manual routing
Backlog (dependency order):
1. DB migrations: new tables, constraints, indexes, enums, outbox updates.
2. Task generation idempotent endpoint + transaction + replay store.
3. Routing evaluator library + deterministic conflict checker.
4. Assignment executor + event emission + audit log writes.
5. Reassignment API hard requirement for reason code + feedback persistence.
6. SLA scheduler worker + escalation policy engine.
7. Notification policy engine (immediate/digest/escalation-only) with de-dup.
8. KPI event emitters + dashboards + alert thresholds.
9. Routing simulation endpoint/UI before rule activation.

Cut-over plan:
1. Shadow mode (week 1): compute auto-assignee but do not apply; compare against manual owner and log deltas.
2. Assisted mode (week 2): auto-assign only when confidence >= threshold; rest to manual queue.
3. Guarded auto mode (week 3): enable full auto-assign for pilot projects with rapid rollback flag.
4. Stabilization (week 4): tune priorities/thresholds from feedback; require override reason compliance >= 95%.

Rollback controls:
- Per-project feature flag `routing_auto_assign_enabled`.
- Global kill switch for scheduler escalations.
- Safe fallback always routes to manual triage queue with no task-loss risk.

## Task 3

### 1) Revalidated task-generation and routing events against canonical registry
Canonical internal event envelope (locked to Stage 0 contract):
- `event_id` (uuid)
- `event_type` (string)
- `event_version` (integer)
- `organization_id` (uuid)
- `aggregate_type` (string)
- `aggregate_id` (uuid)
- `occurred_at` (timestamptz)
- `produced_by` (string service id)
- `idempotency_key` (string, unique per org in `domain_events`)
- `trace_id` (string)
- `payload` (jsonb)

Registry entries for Stage 1B (v1 only during pilot):
- `tasks.bulk_created_from_extractions` `event_version=1`
  - `aggregate_type=comment_letter`, `aggregate_id=letter_id`, `produced_by=task-generation-service`
  - payload required: `letter_id`, `project_id`, `task_ids[]`, `created_count`, `existing_count`
- `task.auto_assigned` `event_version=1`
  - `aggregate_type=task`, `aggregate_id=task_id`, `produced_by=routing-service`
  - payload required: `task_id`, `assignee_id`, `rule_id`, `confidence`, `assignment_mode`
- `task.assignment_overdue` `event_version=1`
  - `aggregate_type=task`, `aggregate_id=task_id`, `produced_by=sla-reminder-service`
  - payload required: `task_id`, `assignee_id`, `overdue_by_hours`, `escalation_level`, `policy_id`

Validation rules:
- Reject writes to outbox if `event_type` not in registry or `event_version != 1`.
- Additive-only payload changes allowed in v1; breaking changes require v2 event version.
- External webhook naming may include suffix form (`<event_type>.v1`), but internal `domain_events` stays `event_type` + `event_version`.

### 2) DB constraints enforcing one task per approved extraction item
Hard constraints:
- `tasks.source_extraction_id` is required for Stage 1B-generated tasks.
- `unique index ux_tasks_org_source_extraction on tasks(organization_id, source_extraction_id) where source_extraction_id is not null`
  - This is the invariant that blocks duplicates under retries/races.
- `foreign key (source_extraction_id) references comment_extractions(id)`
- `check (assignment_confidence >= 0 and assignment_confidence <= 1)`

Approval-state enforcement:
- Trigger `trg_tasks_source_must_be_approved` before insert/update on `tasks` when `source_extraction_id is not null`:
  - query `comment_extractions.status`; reject unless `status = 'approved'`.
  - reject if referenced extraction belongs to different `project_id`/`organization_id`.

Race/retry-safe generation pattern:
- Execute generation in one transaction.
- `INSERT ... ON CONFLICT (organization_id, source_extraction_id) DO NOTHING`.
- Persist deterministic run record in `task_generation_runs` with unique `(organization_id, idempotency_key)`.
- Emit one outbox row per run with unique `(organization_id, idempotency_key)` to prevent duplicate event emission.

Recommended DDL sketch:
```sql
create unique index if not exists ux_tasks_org_source_extraction
  on tasks (organization_id, source_extraction_id)
  where source_extraction_id is not null;

create table if not exists task_generation_runs (
  id uuid primary key,
  organization_id uuid not null,
  project_id uuid not null,
  letter_id uuid not null,
  idempotency_key text not null,
  request_hash text not null,
  status text not null check (status in ('IN_PROGRESS','COMPLETED','FAILED')),
  created_count integer not null default 0,
  existing_count integer not null default 0,
  created_at timestamptz not null default now(),
  completed_at timestamptz null,
  unique (organization_id, idempotency_key)
);
```

### 3) Contract tests: duplicate requests, duplicate events, reassignment feedback integrity
#### A) Duplicate request tests (task generation API)
1. Same `Idempotency-Key` retried N times:
   - Assert one `task_generation_runs` row.
   - Assert one task per approved extraction (`ux_tasks_org_source_extraction` unchanged).
   - Assert identical response payload on replay (`created_count`, `existing_count`, `task_ids`).
2. Concurrent create requests for same letter (with/without same key):
   - Assert no duplicate tasks.
   - Assert conflict path returns deterministic outcome (`200 replay` or `409 key mismatch` by policy).
3. Request includes unapproved extraction id:
   - Assert transaction fails; zero tasks inserted.

#### B) Duplicate event tests (producer/consumer)
1. Producer retries publish of same run:
   - Assert `domain_events` uniqueness on `(organization_id, idempotency_key)` prevents duplicate event rows.
2. Consumer receives same `event_id` twice:
   - Assert second processing skipped via `event_consumer_dedup(consumer_name,event_id)`.
3. Out-of-order duplicate (`task.auto_assigned` arrives twice around reassignment):
   - Assert assignment state remains correct and idempotent; audit trail contains one effective auto-assignment action.

#### C) Reassignment feedback integrity tests
1. `POST /tasks/{taskId}/reassign` without `feedback_reason_code`:
   - Assert `422` validation failure.
2. Reassignment where `from_assignee_id == to_assignee_id`:
   - Assert reject with `422`.
3. Reassignment succeeds:
   - Assert `task_assignment_feedback` row written with:
     - non-null `task_id`, `actor_user_id`, `feedback_reason_code`, `was_auto_assigned`
     - `source_rule_id/source_confidence` present when prior assignment was auto.
4. Tamper test for cross-tenant integrity:
   - Assert reassignment cannot reference task/rule outside caller organization/project.

Operability gates before Stage 1B pilot cut-over:
- All tests above run in CI on every schema or contract change.
- Contract snapshot tests pin event payloads for `event_version=1`.
- Migration guard checks verify `ux_tasks_org_source_extraction` exists in production before enabling auto-generation.
