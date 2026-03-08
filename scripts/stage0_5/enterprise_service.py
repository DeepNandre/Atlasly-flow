from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import uuid


WEBHOOK_WRITE_ROLES = {"owner", "admin"}
CONNECTOR_TRIGGER_ROLES = {"owner", "admin", "pm"}
DASHBOARD_READ_ROLES = {"owner", "admin", "pm", "reviewer"}
API_KEY_WRITE_ROLES = {"owner", "admin"}
TASK_TEMPLATE_WRITE_ROLES = {"owner", "admin", "pm"}
AUDIT_EXPORT_ROLES = {"owner", "admin"}

ALLOWED_WEBHOOK_EVENT_NAMES = {
    "document.uploaded",
    "document.ocr_completed",
    "task.created",
    "task.assigned",
    "permit.status_changed",
    "integration.run_started",
    "integration.run_completed",
    "webhook.delivery_failed",
}

ALLOWED_CONNECTOR_NAMES = {"accela_api", "opengov_api", "cloudpermit_portal_runner"}
ALLOWED_CONNECTOR_FINAL_STATUSES = {"succeeded", "partial", "failed", "cancelled"}

ALLOWED_API_SCOPES = {
    "webhooks:read",
    "webhooks:write",
    "connectors:read",
    "connectors:run",
    "dashboard:read",
    "tasks:read",
    "tasks:write",
    "audit:read",
}

ALLOWED_CONNECTOR_ERROR_CLASSIFICATIONS = {
    "auth.invalid_credentials",
    "auth.expired_token",
    "rate_limit.exceeded",
    "upstream.timeout",
    "upstream.unavailable",
    "schema.mismatch",
    "data.validation_failed",
    "permission.denied",
    "internal.transient",
    "internal.fatal",
}

DEFAULT_RETRYABLE_CLASSIFICATIONS = {
    "rate_limit.exceeded",
    "upstream.timeout",
    "upstream.unavailable",
    "internal.transient",
}

RETRY_DELAYS_SECONDS = {
    1: 30,
    2: 120,
    3: 600,
    4: 1800,
    5: 7200,
    6: 28800,
}

DASHBOARD_REQUIRED_METRICS = {
    "permits_total",
    "permit_cycle_time_p50_days",
    "permit_cycle_time_p90_days",
    "corrections_rate",
    "approval_rate_30d",
    "task_sla_breach_rate",
    "connector_health_score",
    "webhook_delivery_success_rate",
}

DEFAULT_API_KEY_MAX_AGE_DAYS = 90
DEFAULT_API_KEY_ROTATION_WARNING_DAYS = 14

PROD_LIKE_DEPLOYMENT_TIERS = {"mvp", "public_mvp", "prod"}
NON_PRODUCTION_RUNTIME_BACKENDS = {"in_memory"}


class EnterpriseReadinessError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    requester_role: str
    user_id: str | None = None


@dataclass
class EnterpriseStore:
    webhook_subscriptions_by_id: dict[str, dict]
    webhook_sub_by_org_idempotency: dict[tuple[str, str], str]
    webhook_active_by_org_target: dict[tuple[str, str], str]
    webhook_deliveries_by_id: dict[str, dict]
    webhook_delivery_by_key: dict[tuple[str, str, int], str]
    webhook_dead_letters_by_delivery: dict[str, dict]
    webhook_replay_jobs_by_id: dict[str, dict]

    connector_runs_by_id: dict[str, dict]
    connector_run_by_org_connector_idempotency: dict[tuple[str, str, str], str]
    connector_errors_by_id: dict[str, dict]

    dashboard_snapshots_by_org: dict[str, list[dict]]
    dashboard_snapshot_by_org_ts: dict[tuple[str, str], str]

    api_credentials_by_id: dict[str, dict]
    api_cred_active_by_org_prefix: dict[tuple[str, str], str]
    api_cred_by_org_idempotency: dict[tuple[str, str], str]

    task_templates_by_id: dict[str, dict]
    task_template_active_name_key: dict[tuple[str, str], str]

    security_audit_exports_by_id: dict[str, dict]

    outbox_events: list[dict]

    @classmethod
    def empty(cls) -> "EnterpriseStore":
        return cls(
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            [],
        )


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def enforce_runtime_hardening_boundary(
    *,
    runtime_backend: str,
    deployment_tier: str,
    persistence_ready: bool | None = None,
) -> None:
    tier = deployment_tier.strip().lower()
    backend = runtime_backend.strip().lower()

    if tier not in PROD_LIKE_DEPLOYMENT_TIERS:
        return

    if backend in NON_PRODUCTION_RUNTIME_BACKENDS:
        raise EnterpriseReadinessError(
            503,
            "runtime_not_hardened",
            "in-memory runtime backend is NOT PRODUCTION READY for MVP/public deployments",
        )

    if persistence_ready is False:
        raise EnterpriseReadinessError(
            503,
            "persistence_not_ready",
            "persistence adapter is not production-capable for MVP/public deployments",
        )

    if persistence_ready is None:
        raise EnterpriseReadinessError(
            503,
            "persistence_check_missing",
            "production-like deployments require explicit persistence readiness signal",
        )


def _require_role(auth_context: AuthContext, allowed_roles: set[str], action: str) -> None:
    if auth_context.requester_role not in allowed_roles:
        raise EnterpriseReadinessError(403, "forbidden", f"role cannot {action}")


def _event_envelope(
    *,
    event_type: str,
    organization_id: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    produced_by: str,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": _iso(occurred_at),
        "produced_by": produced_by,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def _validate_webhook_url(target_url: str) -> str:
    url = target_url.strip()
    if not url:
        raise EnterpriseReadinessError(422, "validation_error", "target_url is required")
    if not url.lower().startswith("https://"):
        raise EnterpriseReadinessError(422, "validation_error", "target_url must be https")
    return url


def _validate_webhook_events(event_types: list[str]) -> list[str]:
    if not event_types:
        raise EnterpriseReadinessError(422, "validation_error", "event_types must not be empty")
    normalized = [str(v).strip() for v in event_types if str(v).strip()]
    if not normalized:
        raise EnterpriseReadinessError(422, "validation_error", "event_types must not be empty")
    invalid = sorted(set(normalized) - ALLOWED_WEBHOOK_EVENT_NAMES)
    if invalid:
        raise EnterpriseReadinessError(
            422,
            "validation_error",
            f"unsupported webhook event type(s): {', '.join(invalid)}",
        )
    return sorted(set(normalized))


def _validate_api_scopes(scopes: list[str]) -> list[str]:
    if not scopes:
        raise EnterpriseReadinessError(422, "validation_error", "scopes must not be empty")
    normalized = [str(v).strip() for v in scopes if str(v).strip()]
    invalid = sorted(set(normalized) - ALLOWED_API_SCOPES)
    if invalid:
        raise EnterpriseReadinessError(
            422,
            "validation_error",
            f"unsupported scope(s): {', '.join(invalid)}",
        )
    return sorted(set(normalized))


def register_webhook_subscription(
    *,
    target_url: str,
    event_types: list[str],
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, WEBHOOK_WRITE_ROLES, "register webhook subscriptions")
    if not idempotency_key.strip():
        raise EnterpriseReadinessError(400, "invalid_request", "Idempotency-Key is required")

    ts = now or datetime.now(timezone.utc)
    org_id = auth_context.organization_id
    normalized_url = _validate_webhook_url(target_url)
    normalized_events = _validate_webhook_events(event_types)

    idem = (org_id, idempotency_key)
    existing_id = store.webhook_sub_by_org_idempotency.get(idem)
    if existing_id:
        return 200, store.webhook_subscriptions_by_id[existing_id]

    active_key = (org_id, normalized_url)
    existing_active = store.webhook_active_by_org_target.get(active_key)
    if existing_active:
        raise EnterpriseReadinessError(
            409,
            "conflict",
            "active webhook subscription already exists for organization and target_url",
        )

    sub_id = str(uuid.uuid4())
    record = {
        "subscription_id": sub_id,
        "organization_id": org_id,
        "target_url": normalized_url,
        "event_types": normalized_events,
        "verification_status": "pending",
        "is_active": True,
        "consecutive_failures": 0,
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.webhook_subscriptions_by_id[sub_id] = record
    store.webhook_sub_by_org_idempotency[idem] = sub_id
    store.webhook_active_by_org_target[active_key] = sub_id
    return 201, record


def list_webhook_events(
    *,
    auth_context: AuthContext,
    store: EnterpriseStore,
    subscription_id: str | None = None,
    status: str | None = None,
    from_iso: str | None = None,
    to_iso: str | None = None,
    attempt_gte: int | None = None,
    limit: int = 100,
) -> tuple[int, dict]:
    if limit < 1 or limit > 500:
        raise EnterpriseReadinessError(422, "validation_error", "limit must be between 1 and 500")

    from_ts = _parse_iso(from_iso) if from_iso else None
    to_ts = _parse_iso(to_iso) if to_iso else None
    if from_ts and to_ts and from_ts > to_ts:
        raise EnterpriseReadinessError(422, "validation_error", "from must be <= to")

    if subscription_id:
        sub = store.webhook_subscriptions_by_id.get(subscription_id)
        if not sub:
            raise EnterpriseReadinessError(404, "not_found", "subscription not found")
        if sub["organization_id"] != auth_context.organization_id:
            raise EnterpriseReadinessError(403, "forbidden", "subscription belongs to another organization")

    rows = []
    for row in store.webhook_deliveries_by_id.values():
        if row["organization_id"] != auth_context.organization_id:
            continue
        if subscription_id and row["subscription_id"] != subscription_id:
            continue
        if status and row["status"] != status:
            continue
        if attempt_gte is not None and int(row["attempt"]) < int(attempt_gte):
            continue
        created_at = _parse_iso(row["created_at"])
        if from_ts and created_at < from_ts:
            continue
        if to_ts and created_at > to_ts:
            continue
        rows.append(row)

    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return 200, {"items": rows[:limit], "count": len(rows)}


def _failure_is_retryable(response_code: int | None) -> bool:
    if response_code is None:
        return True
    if response_code in {408, 429}:
        return True
    if response_code >= 500:
        return True
    return False


def _retry_next_at(attempt: int, now: datetime) -> str | None:
    delay = RETRY_DELAYS_SECONDS.get(attempt)
    if delay is None:
        return None
    return _iso(now + timedelta(seconds=delay))


def record_webhook_delivery_attempt(
    *,
    subscription_id: str,
    event_id: str,
    event_name: str,
    payload: dict,
    attempt: int,
    response_code: int | None,
    error_code: str | None,
    error_detail: str | None,
    trace_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    ts = now or datetime.now(timezone.utc)
    sub = store.webhook_subscriptions_by_id.get(subscription_id)
    if not sub:
        raise EnterpriseReadinessError(404, "not_found", "subscription not found")
    if sub["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "subscription belongs to another organization")

    if attempt <= 0:
        raise EnterpriseReadinessError(422, "validation_error", "attempt must be > 0")

    dedupe = (subscription_id, event_id, attempt)
    existing_id = store.webhook_delivery_by_key.get(dedupe)
    if existing_id:
        return store.webhook_deliveries_by_id[existing_id]

    max_attempts = 7
    status = "delivered"
    next_retry_at = None
    is_terminal = True

    if response_code is None or not (200 <= response_code <= 299):
        retryable = _failure_is_retryable(response_code)
        if retryable and attempt < max_attempts:
            status = "retrying"
            is_terminal = False
            next_retry_at = _retry_next_at(attempt, ts)
        elif retryable:
            status = "dead_lettered"
        else:
            status = "failed_non_retryable"

    delivery_id = str(uuid.uuid4())
    record = {
        "delivery_id": delivery_id,
        "organization_id": sub["organization_id"],
        "subscription_id": subscription_id,
        "event_id": event_id,
        "event_name": event_name,
        "attempt": attempt,
        "status": status,
        "response_code": response_code,
        "error_code": error_code,
        "error_detail": error_detail,
        "payload": dict(payload),
        "next_retry_at": next_retry_at,
        "is_terminal": is_terminal,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }

    store.webhook_deliveries_by_id[delivery_id] = record
    store.webhook_delivery_by_key[dedupe] = delivery_id

    if status in {"dead_lettered", "failed_non_retryable"}:
        dead_letter = {
            "dead_letter_id": str(uuid.uuid4()),
            "organization_id": sub["organization_id"],
            "delivery_id": delivery_id,
            "subscription_id": subscription_id,
            "event_id": event_id,
            "event_name": event_name,
            "final_attempt": attempt,
            "error_code": error_code,
            "error_detail": error_detail,
            "replay_status": "not_requested",
            "created_at": _iso(ts),
        }
        store.webhook_dead_letters_by_delivery[delivery_id] = dead_letter

        store.outbox_events.append(
            _event_envelope(
                event_type="webhook.delivery_failed",
                organization_id=sub["organization_id"],
                aggregate_type="webhook_delivery",
                aggregate_id=delivery_id,
                idempotency_key=f"{delivery_id}:webhook.delivery_failed:v1",
                trace_id=trace_id,
                payload={
                    "subscription_id": subscription_id,
                    "event_id": event_id,
                    "attempt": attempt,
                    "error_code": error_code or "unknown_error",
                },
                produced_by="webhook-dispatcher",
                occurred_at=ts,
            )
        )
    return record


def request_webhook_replay(
    *,
    delivery_id: str,
    reason: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, WEBHOOK_WRITE_ROLES, "request webhook replay")
    ts = now or datetime.now(timezone.utc)

    dead_letter = store.webhook_dead_letters_by_delivery.get(delivery_id)
    if not dead_letter:
        raise EnterpriseReadinessError(404, "not_found", "dead letter not found for delivery")
    if dead_letter["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "delivery belongs to another organization")

    replay_id = str(uuid.uuid4())
    replay = {
        "replay_job_id": replay_id,
        "organization_id": auth_context.organization_id,
        "delivery_id": delivery_id,
        "status": "queued",
        "reason": reason,
        "requested_by": auth_context.user_id,
        "created_at": _iso(ts),
    }
    store.webhook_replay_jobs_by_id[replay_id] = replay
    dead_letter["replay_status"] = "queued"
    dead_letter["replay_job_id"] = replay_id
    return replay


def trigger_connector_sync(
    *,
    connector_name: str,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    run_mode: str = "delta",
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, CONNECTOR_TRIGGER_ROLES, "trigger connector sync")
    if not idempotency_key.strip():
        raise EnterpriseReadinessError(400, "invalid_request", "Idempotency-Key is required")

    normalized = connector_name.strip().lower()
    if normalized not in ALLOWED_CONNECTOR_NAMES:
        raise EnterpriseReadinessError(422, "validation_error", "unsupported connector")
    if run_mode not in {"delta", "full"}:
        raise EnterpriseReadinessError(422, "validation_error", "run_mode must be delta|full")

    ts = now or datetime.now(timezone.utc)
    key = (auth_context.organization_id, normalized, idempotency_key)
    existing = store.connector_run_by_org_connector_idempotency.get(key)
    if existing:
        return 200, store.connector_runs_by_id[existing]

    run_id = str(uuid.uuid4())
    run = {
        "run_id": run_id,
        "organization_id": auth_context.organization_id,
        "connector_name": normalized,
        "run_status": "running",
        "run_mode": run_mode,
        "trigger_type": "manual",
        "started_at": _iso(ts),
        "ended_at": None,
        "duration_ms": None,
        "records_fetched": 0,
        "records_synced": 0,
        "records_failed": 0,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.connector_runs_by_id[run_id] = run
    store.connector_run_by_org_connector_idempotency[key] = run_id

    store.outbox_events.append(
        _event_envelope(
            event_type="integration.run_started",
            organization_id=auth_context.organization_id,
            aggregate_type="connector_run",
            aggregate_id=run_id,
            idempotency_key=f"{run_id}:integration.run_started:v1",
            trace_id=trace_id,
            payload={
                "connector": normalized,
                "organization_id": auth_context.organization_id,
                "run_id": run_id,
                "started_at": _iso(ts),
            },
            produced_by="integration-service",
            occurred_at=ts,
        )
    )
    return 202, run


def complete_connector_sync(
    *,
    run_id: str,
    final_status: str,
    records_fetched: int,
    records_synced: int,
    records_failed: int,
    trace_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    if final_status not in ALLOWED_CONNECTOR_FINAL_STATUSES:
        raise EnterpriseReadinessError(422, "validation_error", "invalid final_status")

    run = store.connector_runs_by_id.get(run_id)
    if not run:
        raise EnterpriseReadinessError(404, "not_found", "connector run not found")
    if run["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "run belongs to another organization")
    if run["run_status"] in ALLOWED_CONNECTOR_FINAL_STATUSES:
        raise EnterpriseReadinessError(409, "invalid_state", "connector run already terminal")

    if min(records_fetched, records_synced, records_failed) < 0:
        raise EnterpriseReadinessError(422, "validation_error", "record counters must be non-negative")
    if records_synced > records_fetched:
        raise EnterpriseReadinessError(422, "validation_error", "records_synced cannot exceed records_fetched")

    ts = now or datetime.now(timezone.utc)
    started_at = _parse_iso(run["started_at"])
    duration_ms = int(max(0.0, (ts - started_at).total_seconds() * 1000))

    run["run_status"] = final_status
    run["ended_at"] = _iso(ts)
    run["duration_ms"] = duration_ms
    run["records_fetched"] = records_fetched
    run["records_synced"] = records_synced
    run["records_failed"] = records_failed
    run["updated_at"] = _iso(ts)

    store.outbox_events.append(
        _event_envelope(
            event_type="integration.run_completed",
            organization_id=auth_context.organization_id,
            aggregate_type="connector_run",
            aggregate_id=run_id,
            idempotency_key=f"{run_id}:integration.run_completed:v1",
            trace_id=trace_id,
            payload={
                "run_id": run_id,
                "status": final_status,
                "duration_ms": duration_ms,
                "records_synced": records_synced,
            },
            produced_by="integration-service",
            occurred_at=ts,
        )
    )
    return run


def record_connector_error(
    *,
    run_id: str,
    classification: str,
    message: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    external_code: str | None = None,
    external_record_id: str | None = None,
    payload_excerpt_redacted: dict | None = None,
    is_retryable: bool | None = None,
    now: datetime | None = None,
) -> dict:
    run = store.connector_runs_by_id.get(run_id)
    if not run:
        raise EnterpriseReadinessError(404, "not_found", "connector run not found")
    if run["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "run belongs to another organization")

    norm = classification.strip()
    if norm not in ALLOWED_CONNECTOR_ERROR_CLASSIFICATIONS:
        raise EnterpriseReadinessError(422, "validation_error", "unsupported error classification")
    if not message.strip():
        raise EnterpriseReadinessError(422, "validation_error", "message is required")

    ts = now or datetime.now(timezone.utc)
    err_id = str(uuid.uuid4())
    row = {
        "error_id": err_id,
        "organization_id": run["organization_id"],
        "connector_run_id": run_id,
        "classification": norm,
        "message": message,
        "external_code": external_code,
        "external_record_id": external_record_id,
        "payload_excerpt_redacted": payload_excerpt_redacted or {},
        "is_retryable": (
            is_retryable if is_retryable is not None else norm in DEFAULT_RETRYABLE_CLASSIFICATIONS
        ),
        "occurred_at": _iso(ts),
    }
    store.connector_errors_by_id[err_id] = row
    return row


def upsert_dashboard_snapshot(
    *,
    metrics: dict,
    snapshot_at: datetime,
    source_max_event_at: datetime | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    is_backfill: bool = False,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, DASHBOARD_READ_ROLES, "write dashboard snapshot")

    missing = sorted(DASHBOARD_REQUIRED_METRICS - set(metrics.keys()))
    if missing:
        raise EnterpriseReadinessError(422, "validation_error", f"missing KPI metrics: {', '.join(missing)}")

    ts = now or datetime.now(timezone.utc)
    org_id = auth_context.organization_id
    snapshot_ts_iso = _iso(snapshot_at)
    freshness_anchor = source_max_event_at or snapshot_at
    freshness_seconds = int(max(0.0, (ts - freshness_anchor).total_seconds()))

    row = {
        "snapshot_id": str(uuid.uuid4()),
        "organization_id": org_id,
        "snapshot_at": snapshot_ts_iso,
        "source_max_event_at": _iso(source_max_event_at) if source_max_event_at else None,
        "freshness_seconds": freshness_seconds,
        "is_backfill": is_backfill,
        "metrics": dict(metrics),
        "updated_at": _iso(ts),
    }

    key = (org_id, snapshot_ts_iso)
    existing_id = store.dashboard_snapshot_by_org_ts.get(key)
    if existing_id:
        snapshots = store.dashboard_snapshots_by_org.get(org_id, [])
        for idx, existing in enumerate(snapshots):
            if existing["snapshot_id"] == existing_id:
                row["snapshot_id"] = existing_id
                snapshots[idx] = row
                return row

    store.dashboard_snapshots_by_org.setdefault(org_id, []).append(row)
    store.dashboard_snapshot_by_org_ts[key] = row["snapshot_id"]
    return row


def get_dashboard_portfolio(
    *,
    auth_context: AuthContext,
    store: EnterpriseStore,
) -> tuple[int, dict]:
    _require_role(auth_context, DASHBOARD_READ_ROLES, "read dashboard portfolio")
    snapshots = store.dashboard_snapshots_by_org.get(auth_context.organization_id, [])
    if not snapshots:
        raise EnterpriseReadinessError(404, "not_found", "dashboard snapshot not found")

    latest = sorted(snapshots, key=lambda r: r["snapshot_at"], reverse=True)[0]
    return 200, {
        "organization_id": auth_context.organization_id,
        "snapshot_at": latest["snapshot_at"],
        "freshness_seconds": latest["freshness_seconds"],
        "metrics": latest["metrics"],
    }


def _generate_api_key_plaintext(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"


def create_api_key(
    *,
    org_id: str,
    name: str,
    scopes: list[str],
    idempotency_key: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, API_KEY_WRITE_ROLES, "create API keys")
    if auth_context.organization_id != org_id:
        raise EnterpriseReadinessError(403, "forbidden", "cannot create key for another organization")
    if not idempotency_key.strip():
        raise EnterpriseReadinessError(400, "invalid_request", "Idempotency-Key is required")
    if not name.strip():
        raise EnterpriseReadinessError(422, "validation_error", "name is required")

    ts = now or datetime.now(timezone.utc)
    if expires_at and expires_at > ts + timedelta(days=365):
        raise EnterpriseReadinessError(422, "validation_error", "expires_at cannot exceed 365 days")

    normalized_scopes = _validate_api_scopes(scopes)

    idem = (org_id, idempotency_key)
    existing_id = store.api_cred_by_org_idempotency.get(idem)
    if existing_id:
        existing = store.api_credentials_by_id[existing_id]
        replay_payload = {
            "credential_id": existing["credential_id"],
            "name": existing["name"],
            "key_prefix": existing["key_prefix"],
            "scopes": existing["scopes"],
            "created_at": existing["created_at"],
            "expires_at": existing["expires_at"],
            "last_used_at": existing.get("last_used_at"),
            "rotation_due_at": existing.get("rotation_due_at"),
            "one_time_display": False,
        }
        return 200, replay_payload

    prefix = f"ak_live_{uuid.uuid4().hex[:10]}"
    while (org_id, prefix) in store.api_cred_active_by_org_prefix:
        prefix = f"ak_live_{uuid.uuid4().hex[:10]}"

    plaintext = _generate_api_key_plaintext(prefix)
    key_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    cred_id = str(uuid.uuid4())
    row = {
        "credential_id": cred_id,
        "organization_id": org_id,
        "name": name.strip(),
        "key_prefix": prefix,
        "key_hash": key_hash,
        "scopes": normalized_scopes,
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
        "expires_at": _iso(expires_at) if expires_at else None,
        "last_used_at": None,
        "last_used_source": None,
        "rotation_due_at": _iso(ts + timedelta(days=DEFAULT_API_KEY_MAX_AGE_DAYS)),
        "revoked_at": None,
        "revoked_reason": None,
    }

    store.api_credentials_by_id[cred_id] = row
    store.api_cred_active_by_org_prefix[(org_id, prefix)] = cred_id
    store.api_cred_by_org_idempotency[idem] = cred_id

    payload = {
        "credential_id": cred_id,
        "name": row["name"],
        "key_prefix": prefix,
        "plaintext_key": plaintext,
        "scopes": normalized_scopes,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "last_used_at": row["last_used_at"],
        "rotation_due_at": row["rotation_due_at"],
        "one_time_display": True,
    }
    return 201, payload


def revoke_api_key(
    *,
    credential_id: str,
    reason: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, API_KEY_WRITE_ROLES, "revoke API keys")
    ts = now or datetime.now(timezone.utc)

    row = store.api_credentials_by_id.get(credential_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "api credential not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "credential belongs to another organization")
    if row["revoked_at"]:
        raise EnterpriseReadinessError(409, "invalid_state", "credential already revoked")

    row["revoked_at"] = _iso(ts)
    row["revoked_reason"] = reason
    row["revoked_by"] = auth_context.user_id
    store.api_cred_active_by_org_prefix.pop((row["organization_id"], row["key_prefix"]), None)
    return row


def rotate_api_key(
    *,
    credential_id: str,
    new_name: str,
    new_scopes: list[str],
    idempotency_key: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    existing = store.api_credentials_by_id.get(credential_id)
    if not existing:
        raise EnterpriseReadinessError(404, "not_found", "api credential not found")
    revoke_api_key(
        credential_id=credential_id,
        reason="rotated",
        auth_context=auth_context,
        store=store,
        now=now,
    )
    status, payload = create_api_key(
        org_id=existing["organization_id"],
        name=new_name,
        scopes=new_scopes,
        idempotency_key=idempotency_key,
        auth_context=auth_context,
        store=store,
        expires_at=expires_at,
        now=now,
    )
    existing["rotated_at"] = _iso(now or datetime.now(timezone.utc))
    return status, payload


def mark_api_key_used(
    *,
    credential_id: str,
    usage_source: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, API_KEY_WRITE_ROLES, "record API key usage")
    row = store.api_credentials_by_id.get(credential_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "api credential not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "credential belongs to another organization")
    if row.get("revoked_at"):
        raise EnterpriseReadinessError(409, "invalid_state", "credential is revoked")
    if row.get("expires_at"):
        expires_at = _parse_iso(str(row["expires_at"]))
        if expires_at <= (now or datetime.now(timezone.utc)):
            raise EnterpriseReadinessError(409, "invalid_state", "credential is expired")

    ts = now or datetime.now(timezone.utc)
    source = usage_source.strip() or "unknown"
    row["last_used_at"] = _iso(ts)
    row["last_used_source"] = source[:120]
    return row


def scan_api_key_rotation_policy(
    *,
    auth_context: AuthContext,
    store: EnterpriseStore,
    max_age_days: int = DEFAULT_API_KEY_MAX_AGE_DAYS,
    warning_days: int = DEFAULT_API_KEY_ROTATION_WARNING_DAYS,
    auto_revoke_overdue: bool = False,
    now: datetime | None = None,
) -> dict:
    allowed_roles = API_KEY_WRITE_ROLES if auto_revoke_overdue else DASHBOARD_READ_ROLES
    _require_role(auth_context, allowed_roles, "run API key rotation policy")
    ts = now or datetime.now(timezone.utc)
    if max_age_days < 1 or max_age_days > 365:
        raise EnterpriseReadinessError(422, "validation_error", "max_age_days must be between 1 and 365")
    if warning_days < 0 or warning_days > 180:
        raise EnterpriseReadinessError(422, "validation_error", "warning_days must be between 0 and 180")

    overdue: list[dict] = []
    due_soon: list[dict] = []
    compliant: list[dict] = []

    for row in store.api_credentials_by_id.values():
        if row["organization_id"] != auth_context.organization_id:
            continue
        if row.get("revoked_at"):
            continue

        created_at = _parse_iso(str(row["created_at"]))
        policy_due = created_at + timedelta(days=max_age_days)
        configured_due = _parse_iso(str(row["rotation_due_at"])) if row.get("rotation_due_at") else policy_due
        due_at = min(policy_due, configured_due)
        days_until_due = int((due_at - ts).total_seconds() // 86400)

        summary = {
            "credential_id": row["credential_id"],
            "name": row["name"],
            "key_prefix": row["key_prefix"],
            "created_at": row["created_at"],
            "last_used_at": row.get("last_used_at"),
            "rotation_due_at": _iso(due_at),
            "days_until_due": days_until_due,
        }
        if due_at <= ts:
            if auto_revoke_overdue:
                row["revoked_at"] = _iso(ts)
                row["revoked_reason"] = "forced_rotation_policy"
                row["revoked_by"] = auth_context.user_id
                store.api_cred_active_by_org_prefix.pop((row["organization_id"], row["key_prefix"]), None)
                summary["action"] = "revoked"
            else:
                summary["action"] = "none"
            overdue.append(summary)
        elif due_at <= ts + timedelta(days=warning_days):
            due_soon.append(summary)
        else:
            compliant.append(summary)

    return {
        "evaluated_at": _iso(ts),
        "max_age_days": max_age_days,
        "warning_days": warning_days,
        "auto_revoke_overdue": auto_revoke_overdue,
        "counts": {
            "overdue": len(overdue),
            "due_soon": len(due_soon),
            "compliant": len(compliant),
        },
        "overdue": sorted(overdue, key=lambda row: row["days_until_due"]),
        "due_soon": sorted(due_soon, key=lambda row: row["days_until_due"]),
    }


def compute_ops_slo_snapshot(
    *,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, DASHBOARD_READ_ROLES, "read ops SLO snapshot")
    ts = now or datetime.now(timezone.utc)
    window_start = ts - timedelta(hours=24)

    deliveries = [
        row
        for row in store.webhook_deliveries_by_id.values()
        if row["organization_id"] == auth_context.organization_id
    ]
    recent_deliveries = []
    for row in deliveries:
        try:
            created_at = _parse_iso(str(row["created_at"]))
        except ValueError:
            continue
        if created_at >= window_start:
            recent_deliveries.append(row)

    success_states = {"delivered"}
    failure_states = {"dead_lettered", "failed_non_retryable"}
    attempts_total = len(recent_deliveries)
    attempts_succeeded = sum(1 for row in recent_deliveries if row.get("status") in success_states)
    attempts_failed = sum(1 for row in recent_deliveries if row.get("status") in failure_states)
    webhook_success_rate = 1.0 if attempts_total == 0 else round(attempts_succeeded / attempts_total, 4)

    connector_runs = [
        row
        for row in store.connector_runs_by_id.values()
        if row["organization_id"] == auth_context.organization_id
    ]
    recent_runs = []
    for row in connector_runs:
        started_at_raw = row.get("started_at") or row.get("created_at")
        if not started_at_raw:
            continue
        try:
            started_at = _parse_iso(str(started_at_raw))
        except ValueError:
            continue
        if started_at >= window_start:
            recent_runs.append(row)

    connector_total = len(recent_runs)
    connector_success = sum(1 for row in recent_runs if row.get("run_status") == "succeeded")
    connector_partial = sum(1 for row in recent_runs if row.get("run_status") == "partial")
    connector_success_rate = 1.0 if connector_total == 0 else round(connector_success / connector_total, 4)
    replay_queue_depth = sum(1 for row in store.webhook_replay_jobs_by_id.values() if row.get("status") == "queued")
    dead_letter_depth = len(
        [row for row in store.webhook_dead_letters_by_delivery.values() if row["organization_id"] == auth_context.organization_id]
    )

    key_policy = scan_api_key_rotation_policy(
        auth_context=auth_context,
        store=store,
        auto_revoke_overdue=False,
        now=ts,
    )
    incidents = []
    if webhook_success_rate < 0.99:
        incidents.append({"severity": "high", "code": "webhook_slo_breach", "message": "Webhook success rate below 99% in 24h window."})
    if connector_success_rate < 0.985:
        incidents.append({"severity": "medium", "code": "connector_slo_breach", "message": "Connector success rate below 98.5% in 24h window."})
    if dead_letter_depth > 25:
        incidents.append({"severity": "medium", "code": "dead_letter_backlog", "message": "Webhook dead-letter backlog exceeded 25."})
    if key_policy["counts"]["overdue"] > 0:
        incidents.append({"severity": "medium", "code": "api_keys_overdue_rotation", "message": "One or more API credentials are overdue rotation."})

    return {
        "generated_at": _iso(ts),
        "window_hours": 24,
        "webhook": {
            "attempts_total": attempts_total,
            "attempts_succeeded": attempts_succeeded,
            "attempts_failed": attempts_failed,
            "success_rate": webhook_success_rate,
            "dead_letter_depth": dead_letter_depth,
            "replay_queue_depth": replay_queue_depth,
            "target_success_rate": 0.99,
        },
        "connectors": {
            "runs_total": connector_total,
            "runs_succeeded": connector_success,
            "runs_partial": connector_partial,
            "success_rate": connector_success_rate,
            "target_success_rate": 0.985,
        },
        "api_keys": key_policy["counts"],
        "incidents": incidents,
    }


def create_task_template(
    *,
    name: str,
    description: str,
    template: dict,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, TASK_TEMPLATE_WRITE_ROLES, "manage task templates")
    if not name.strip():
        raise EnterpriseReadinessError(422, "validation_error", "name is required")
    if not isinstance(template, dict):
        raise EnterpriseReadinessError(422, "validation_error", "template must be an object")

    key = (auth_context.organization_id, name.strip().lower())
    existing = store.task_template_active_name_key.get(key)
    if existing:
        raise EnterpriseReadinessError(409, "conflict", "active template with this name already exists")

    ts = now or datetime.now(timezone.utc)
    template_id = str(uuid.uuid4())
    row = {
        "template_id": template_id,
        "organization_id": auth_context.organization_id,
        "name": name.strip(),
        "description": description,
        "template": dict(template),
        "version": 1,
        "is_active": True,
        "created_by": auth_context.user_id,
        "updated_by": auth_context.user_id,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.task_templates_by_id[template_id] = row
    store.task_template_active_name_key[key] = template_id
    return row


def update_task_template(
    *,
    template_id: str,
    name: str | None,
    description: str | None,
    template: dict | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, TASK_TEMPLATE_WRITE_ROLES, "manage task templates")
    row = store.task_templates_by_id.get(template_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "task template not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "template belongs to another organization")

    ts = now or datetime.now(timezone.utc)

    if name is not None:
        normalized = name.strip()
        if not normalized:
            raise EnterpriseReadinessError(422, "validation_error", "name must not be empty")
        old_key = (row["organization_id"], row["name"].lower())
        new_key = (row["organization_id"], normalized.lower())
        if old_key != new_key and new_key in store.task_template_active_name_key:
            raise EnterpriseReadinessError(409, "conflict", "active template with this name already exists")
        store.task_template_active_name_key.pop(old_key, None)
        store.task_template_active_name_key[new_key] = template_id
        row["name"] = normalized

    if description is not None:
        row["description"] = description
    if template is not None:
        if not isinstance(template, dict):
            raise EnterpriseReadinessError(422, "validation_error", "template must be an object")
        row["template"] = dict(template)

    row["version"] += 1
    row["updated_by"] = auth_context.user_id
    row["updated_at"] = _iso(ts)
    return row


def archive_task_template(
    *,
    template_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, TASK_TEMPLATE_WRITE_ROLES, "manage task templates")
    row = store.task_templates_by_id.get(template_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "task template not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "template belongs to another organization")
    if not row["is_active"]:
        raise EnterpriseReadinessError(409, "invalid_state", "template already archived")

    ts = now or datetime.now(timezone.utc)
    row["is_active"] = False
    row["archived_at"] = _iso(ts)
    row["archived_by"] = auth_context.user_id
    row["updated_by"] = auth_context.user_id
    row["updated_at"] = _iso(ts)
    key = (row["organization_id"], row["name"].lower())
    store.task_template_active_name_key.pop(key, None)
    return row


def request_security_audit_export(
    *,
    time_range_start: datetime,
    time_range_end: datetime,
    export_type: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, AUDIT_EXPORT_ROLES, "request security audit export")
    if time_range_end < time_range_start:
        raise EnterpriseReadinessError(422, "validation_error", "time_range_end must be >= time_range_start")
    if export_type not in {"audit_timeline", "access_log_bundle", "compliance_evidence_pack"}:
        raise EnterpriseReadinessError(422, "validation_error", "invalid export_type")

    ts = now or datetime.now(timezone.utc)
    export_id = str(uuid.uuid4())
    row = {
        "export_id": export_id,
        "organization_id": auth_context.organization_id,
        "requested_by": auth_context.user_id,
        "time_range_start": _iso(time_range_start),
        "time_range_end": _iso(time_range_end),
        "export_type": export_type,
        "status": "pending",
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.security_audit_exports_by_id[export_id] = row
    return row


def mark_security_audit_export_running(
    *,
    export_id: str,
    generated_by: str | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, AUDIT_EXPORT_ROLES, "manage security audit export")
    row = store.security_audit_exports_by_id.get(export_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "export not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "export belongs to another organization")
    if row["status"] != "pending":
        raise EnterpriseReadinessError(409, "invalid_state", "export must be pending")

    ts = now or datetime.now(timezone.utc)
    row["status"] = "running"
    row["started_at"] = _iso(ts)
    row["generated_by"] = generated_by
    row["updated_at"] = _iso(ts)
    return row


def mark_security_audit_export_completed(
    *,
    export_id: str,
    checksum: str,
    storage_uri: str,
    access_log_ref: str,
    generated_by: str | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, AUDIT_EXPORT_ROLES, "manage security audit export")
    row = store.security_audit_exports_by_id.get(export_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "export not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "export belongs to another organization")
    if row["status"] not in {"pending", "running"}:
        raise EnterpriseReadinessError(409, "invalid_state", "export is not completable")

    ts = now or datetime.now(timezone.utc)
    row["status"] = "completed"
    row["checksum"] = checksum
    row["storage_uri"] = storage_uri
    row["access_log_ref"] = access_log_ref
    row["generated_by"] = generated_by
    row["generated_at"] = _iso(ts)
    row["completed_at"] = _iso(ts)
    row["updated_at"] = _iso(ts)
    return row


def build_security_audit_evidence_pack(
    *,
    export_id: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, AUDIT_EXPORT_ROLES, "read security audit evidence pack")
    row = store.security_audit_exports_by_id.get(export_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "export not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "export belongs to another organization")
    if row.get("status") != "completed":
        raise EnterpriseReadinessError(409, "invalid_state", "evidence pack available only for completed exports")

    ts = now or datetime.now(timezone.utc)
    manifest = {
        "export_id": row["export_id"],
        "organization_id": row["organization_id"],
        "export_type": row["export_type"],
        "time_range_start": row["time_range_start"],
        "time_range_end": row["time_range_end"],
        "checksum": row.get("checksum"),
        "storage_uri": row.get("storage_uri"),
        "access_log_ref": row.get("access_log_ref"),
        "generated_at": row.get("generated_at"),
    }
    evidence = {
        "evidence_pack_id": str(uuid.uuid4()),
        "generated_at": _iso(ts),
        "generated_by": auth_context.user_id,
        "manifest": manifest,
    }
    row["evidence_pack"] = evidence
    row["updated_at"] = _iso(ts)
    return evidence


def mark_security_audit_export_failed(
    *,
    export_id: str,
    failure_reason: str,
    auth_context: AuthContext,
    store: EnterpriseStore,
    now: datetime | None = None,
) -> dict:
    _require_role(auth_context, AUDIT_EXPORT_ROLES, "manage security audit export")
    row = store.security_audit_exports_by_id.get(export_id)
    if not row:
        raise EnterpriseReadinessError(404, "not_found", "export not found")
    if row["organization_id"] != auth_context.organization_id:
        raise EnterpriseReadinessError(403, "forbidden", "export belongs to another organization")
    if row["status"] not in {"pending", "running"}:
        raise EnterpriseReadinessError(409, "invalid_state", "export is not fail-able")

    ts = now or datetime.now(timezone.utc)
    row["status"] = "failed"
    row["failure_reason"] = failure_reason
    row["failed_at"] = _iso(ts)
    row["updated_at"] = _iso(ts)
    return row
