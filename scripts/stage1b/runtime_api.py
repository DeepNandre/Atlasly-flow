from __future__ import annotations

from datetime import datetime, timezone
import uuid

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.notification_policy import process_notification_event
from scripts.stage1b.routing_engine import process_overdue_assignments
from scripts.stage1b.tasking_api import Stage1BRequestError
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore
from scripts.stage1b.ticketing_service import ensure_store_defaults
from scripts.stage1b.ticketing_service import reassign_task
from scripts.stage1b.workflow_orchestrator import run_stage1b_workflow


def _error_response(exc: Stage1BRequestError) -> tuple[int, dict]:
    return exc.status, {"error": {"code": exc.code, "message": exc.message}}


def _trace_id(headers: dict[str, str] | None) -> str:
    if headers and headers.get("X-Trace-Id", "").strip():
        return headers["X-Trace-Id"].strip()
    return str(uuid.uuid4())


def post_create_tasks(
    *,
    letter_id: str,
    request_body: dict[str, object] | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    ticket_store: TicketingStore,
    notification_store: NotificationStore,
    confidence_threshold: float = 0.75,
    escalation_policy: dict | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        workflow = run_stage1b_workflow(
            letter_id=letter_id,
            request_body=request_body or {},
            idempotency_key=(headers or {}).get("Idempotency-Key"),
            trace_id=_trace_id(headers),
            auth_context=auth_context,
            ticket_store=ticket_store,
            notification_store=notification_store,
            confidence_threshold=confidence_threshold,
            escalation_policy=escalation_policy,
            now=now,
        )
    except Stage1BRequestError as exc:
        return _error_response(exc)

    return workflow.create_status, {
        "letter_id": letter_id,
        "created_count": workflow.created_count,
        "existing_count": workflow.existing_count,
        "task_ids": workflow.task_ids,
        "auto_assigned_count": workflow.auto_assigned_count,
        "manual_queue_count": workflow.manual_queue_count,
        "escalation_started_count": workflow.escalation_started_count,
        "kpi_snapshot": workflow.kpi_snapshot,
    }


def post_reassign_task(
    *,
    task_id: str,
    request_body: dict[str, object] | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    ticket_store: TicketingStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        status, payload = reassign_task(
            task_id=task_id,
            payload=request_body or {},
            auth_context=auth_context,
            store=ticket_store,
            now=now,
        )
        return status, payload
    except Stage1BRequestError as exc:
        return _error_response(exc)


def run_assignment_overdue_worker(
    *,
    ticket_store: TicketingStore,
    notification_store: NotificationStore,
    user_mode: str = "immediate",
    tick_key: str | None = None,
    now: datetime | None = None,
) -> dict:
    ensure_store_defaults(ticket_store)
    ts = now or datetime.now(timezone.utc)
    normalized_tick = str(tick_key or "").strip()
    if normalized_tick:
        existing = ticket_store.overdue_ticks_by_key.get(normalized_tick)
        if existing:
            replay = dict(existing)
            replay["replayed"] = True
            return replay

    trace_id = str(uuid.uuid4())
    overdue_events = process_overdue_assignments(
        trace_id=trace_id,
        store=ticket_store,
        now=ts,
    )

    sent = 0
    digest = 0
    suppressed = 0
    for event in overdue_events:
        assignee_id = event.get("payload", {}).get("assignee_id")
        if not assignee_id:
            suppressed += 1
            continue
        outcome = process_notification_event(
            event=event,
            user_id=assignee_id,
            user_mode=user_mode,
            notification_store=notification_store,
            now=ts,
        )
        if outcome == "sent_immediate":
            sent += 1
        elif outcome == "digest_queued":
            digest += 1
        else:
            suppressed += 1

    result = {
        "processed_events": len(overdue_events),
        "notifications_sent": sent,
        "digest_queued": digest,
        "suppressed": suppressed,
    }
    if normalized_tick:
        ticket_store.overdue_ticks_by_key[normalized_tick] = dict(result)
        result["tick_key"] = normalized_tick
    return result
