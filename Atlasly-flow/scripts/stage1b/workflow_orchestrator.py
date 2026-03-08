from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from scripts.stage1b.kpi_metrics import compute_operability
from scripts.stage1b.kpi_metrics import compute_routing_quality
from scripts.stage1b.kpi_metrics import compute_triage_velocity
from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.notification_policy import process_notification_event
from scripts.stage1b.routing_engine import auto_assign_task
from scripts.stage1b.routing_engine import create_escalation
from scripts.stage1b.ticketing_service import AuthContext
from scripts.stage1b.ticketing_service import TicketingStore
from scripts.stage1b.ticketing_service import create_tasks_from_approved_extractions


@dataclass
class WorkflowResult:
    create_status: int
    created_count: int
    existing_count: int
    auto_assigned_count: int
    manual_queue_count: int
    escalation_started_count: int
    task_ids: list[str]
    kpi_snapshot: dict


def run_stage1b_workflow(
    *,
    letter_id: str,
    request_body: dict[str, object],
    idempotency_key: str | None,
    trace_id: str,
    auth_context: AuthContext,
    ticket_store: TicketingStore,
    notification_store: NotificationStore,
    user_mode: str = "immediate",
    confidence_threshold: float = 0.75,
    escalation_policy: dict | None = None,
    now: datetime | None = None,
) -> WorkflowResult:
    ts = now or datetime.now(timezone.utc)
    create_status, create_response = create_tasks_from_approved_extractions(
        letter_id=letter_id,
        request_body=request_body,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        auth_context=auth_context,
        store=ticket_store,
        now=ts,
    )

    auto_assigned_count = 0
    manual_queue_count = 0
    escalation_started_count = 0

    # Replay must be side-effect free to keep routing/escalation deterministic.
    if create_status == 200:
        kpi_snapshot = {
            "routing_quality": compute_routing_quality(ticket_store),
            "triage_velocity": compute_triage_velocity(ticket_store, letter_id=letter_id),
            "operability": compute_operability(ticket_store),
        }
        return WorkflowResult(
            create_status=create_status,
            created_count=create_response["created_count"],
            existing_count=create_response["existing_count"],
            auto_assigned_count=0,
            manual_queue_count=0,
            escalation_started_count=0,
            task_ids=list(create_response["task_ids"]),
            kpi_snapshot=kpi_snapshot,
        )

    for task_id in create_response["task_ids"]:
        task = ticket_store.tasks_by_id.get(task_id)
        if not task or task.get("assignee_user_id"):
            continue

        assignment = auto_assign_task(
            task_id=task_id,
            trace_id=trace_id,
            store=ticket_store,
            confidence_threshold=confidence_threshold,
            now=ts,
        )

        if assignment["status"] == "ASSIGNED":
            auto_assigned_count += 1
            event = ticket_store.outbox_events[-1]
            process_notification_event(
                event=event,
                user_id=assignment["assignee_id"],
                user_mode=user_mode,
                notification_store=notification_store,
                now=ts,
            )
            if escalation_policy is not None:
                create_escalation(task_id=task_id, policy=escalation_policy, store=ticket_store, now=ts)
                escalation_started_count += 1
        else:
            manual_queue_count += 1
            ticket_store.manual_queue_by_task_id[task_id] = {
                "task_id": task_id,
                "reason": assignment["reason"],
                "confidence": assignment["confidence"],
                "rule_id": assignment.get("rule_id"),
                "queued_at": ts.isoformat(),
            }
            process_notification_event(
                event={
                    "event_id": f"manual-{task_id}",
                    "event_type": "task.manual_queue_entered",
                    "aggregate_id": task_id,
                    "payload": {"task_id": task_id, "reason": assignment["reason"]},
                },
                user_id=auth_context.user_id,
                user_mode=user_mode,
                notification_store=notification_store,
                now=ts,
            )

    kpi_snapshot = {
        "routing_quality": compute_routing_quality(ticket_store),
        "triage_velocity": compute_triage_velocity(ticket_store, letter_id=letter_id),
        "operability": compute_operability(ticket_store),
    }

    return WorkflowResult(
        create_status=create_status,
        created_count=create_response["created_count"],
        existing_count=create_response["existing_count"],
        auto_assigned_count=auto_assigned_count,
        manual_queue_count=manual_queue_count,
        escalation_started_count=escalation_started_count,
        task_ids=list(create_response["task_ids"]),
        kpi_snapshot=kpi_snapshot,
    )
