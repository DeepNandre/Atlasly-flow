from __future__ import annotations

from datetime import datetime
import uuid

from scripts.stage0_5.enterprise_service import AuthContext
from scripts.stage0_5.enterprise_service import enforce_runtime_hardening_boundary
from scripts.stage0_5.enterprise_service import EnterpriseReadinessError
from scripts.stage0_5.enterprise_service import EnterpriseStore
from scripts.stage0_5.enterprise_service import create_api_key
from scripts.stage0_5.enterprise_service import get_dashboard_portfolio
from scripts.stage0_5.enterprise_service import list_webhook_events
from scripts.stage0_5.enterprise_service import register_webhook_subscription
from scripts.stage0_5.enterprise_service import trigger_connector_sync


def _error_response(exc: EnterpriseReadinessError) -> tuple[int, dict]:
    return exc.status, {"error": {"code": exc.code, "message": exc.message}}


def _trace_id(headers: dict[str, str] | None) -> str:
    if headers and headers.get("X-Trace-Id", "").strip():
        return headers["X-Trace-Id"].strip()
    return str(uuid.uuid4())


def _enforce_hardening(
    *,
    runtime_backend: str,
    deployment_tier: str,
    persistence_ready: bool | None,
) -> None:
    enforce_runtime_hardening_boundary(
        runtime_backend=runtime_backend,
        deployment_tier=deployment_tier,
        persistence_ready=persistence_ready,
    )


def post_webhooks(
    *,
    request_body: dict[str, object] | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    runtime_backend: str = "in_memory",
    deployment_tier: str = "dev",
    persistence_ready: bool | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        _enforce_hardening(
            runtime_backend=runtime_backend,
            deployment_tier=deployment_tier,
            persistence_ready=persistence_ready,
        )
        body = request_body or {}
        return register_webhook_subscription(
            target_url=str(body.get("target_url") or ""),
            event_types=[str(v) for v in (body.get("event_types") or [])],
            idempotency_key=(headers or {}).get("Idempotency-Key", ""),
            trace_id=_trace_id(headers),
            auth_context=auth_context,
            store=store,
            now=now,
        )
    except EnterpriseReadinessError as exc:
        return _error_response(exc)


def get_webhook_events_api(
    *,
    query_params: dict[str, object] | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    runtime_backend: str = "in_memory",
    deployment_tier: str = "dev",
    persistence_ready: bool | None = None,
) -> tuple[int, dict]:
    try:
        _enforce_hardening(
            runtime_backend=runtime_backend,
            deployment_tier=deployment_tier,
            persistence_ready=persistence_ready,
        )
        qp = query_params or {}
        return list_webhook_events(
            auth_context=auth_context,
            store=store,
            subscription_id=str(qp.get("subscription_id")) if qp.get("subscription_id") else None,
            status=str(qp.get("status")) if qp.get("status") else None,
            from_iso=str(qp.get("from")) if qp.get("from") else None,
            to_iso=str(qp.get("to")) if qp.get("to") else None,
            attempt_gte=int(qp["attempt_gte"]) if qp.get("attempt_gte") is not None else None,
            limit=int(qp.get("limit", 100)),
        )
    except EnterpriseReadinessError as exc:
        return _error_response(exc)


def post_connector_sync(
    *,
    connector_name: str,
    request_body: dict[str, object] | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    runtime_backend: str = "in_memory",
    deployment_tier: str = "dev",
    persistence_ready: bool | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        _enforce_hardening(
            runtime_backend=runtime_backend,
            deployment_tier=deployment_tier,
            persistence_ready=persistence_ready,
        )
        body = request_body or {}
        return trigger_connector_sync(
            connector_name=connector_name,
            idempotency_key=(headers or {}).get("Idempotency-Key", ""),
            trace_id=_trace_id(headers),
            auth_context=auth_context,
            store=store,
            run_mode=str(body.get("run_mode") or "delta"),
            now=now,
        )
    except EnterpriseReadinessError as exc:
        return _error_response(exc)


def get_dashboard_portfolio_api(
    *,
    auth_context: AuthContext,
    store: EnterpriseStore,
    runtime_backend: str = "in_memory",
    deployment_tier: str = "dev",
    persistence_ready: bool | None = None,
) -> tuple[int, dict]:
    try:
        _enforce_hardening(
            runtime_backend=runtime_backend,
            deployment_tier=deployment_tier,
            persistence_ready=persistence_ready,
        )
        return get_dashboard_portfolio(auth_context=auth_context, store=store)
    except EnterpriseReadinessError as exc:
        return _error_response(exc)


def post_org_api_keys(
    *,
    org_id: str,
    request_body: dict[str, object] | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: EnterpriseStore,
    runtime_backend: str = "in_memory",
    deployment_tier: str = "dev",
    persistence_ready: bool | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        _enforce_hardening(
            runtime_backend=runtime_backend,
            deployment_tier=deployment_tier,
            persistence_ready=persistence_ready,
        )
        body = request_body or {}
        expires_raw = body.get("expires_at")
        expires_at = None
        if expires_raw:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        return create_api_key(
            org_id=org_id,
            name=str(body.get("name") or ""),
            scopes=[str(v) for v in (body.get("scopes") or [])],
            idempotency_key=(headers or {}).get("Idempotency-Key", ""),
            auth_context=auth_context,
            store=store,
            expires_at=expires_at,
            now=now,
        )
    except EnterpriseReadinessError as exc:
        return _error_response(exc)
    except Exception:
        return 422, {"error": {"code": "validation_error", "message": "invalid expires_at"}}
