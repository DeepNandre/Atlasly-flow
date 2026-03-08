from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from scripts.stage1b.tasking_api import Stage1BRequestError
from scripts.stage1b.ticketing_service import append_outbox_event
from scripts.stage1b.ticketing_service import ensure_store_defaults
from scripts.stage1b.ticketing_service import TicketingStore


def _event_envelope(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    organization_id: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": occurred_at.isoformat(),
        "produced_by": "routing-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def _as_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _matches(rule: dict, task: dict) -> bool:
    if rule.get("organization_id") != task.get("organization_id"):
        return False
    if not rule.get("is_active", False):
        return False
    if rule.get("project_id") is not None and rule.get("project_id") != task.get("project_id"):
        return False
    if rule.get("discipline") is not None and rule.get("discipline") != task.get("discipline"):
        return False
    if rule.get("trade_partner_id") is not None and rule.get("trade_partner_id") != task.get("trade_partner_id"):
        return False
    if rule.get("project_role") is not None and rule.get("project_role") != task.get("project_role"):
        return False
    if rule.get("ahj_id") is not None and rule.get("ahj_id") != task.get("ahj_id"):
        return False
    return True


def _specificity_score(rule: dict) -> int:
    score = 0
    if rule.get("discipline") is not None:
        score += 8
    if rule.get("trade_partner_id") is not None:
        score += 4
    if rule.get("project_role") is not None:
        score += 2
    if rule.get("ahj_id") is not None:
        score += 1
    return score


def _compute_confidence(rule: dict) -> float:
    base = float(rule.get("confidence_base", 0.7))
    boost = _specificity_score(rule) * 0.01
    return min(1.0, round(base + boost, 4))


def select_best_rule(task: dict, rules: list[dict]) -> dict | None:
    ranked: list[tuple] = []
    for rule in rules:
        if not _matches(rule, task):
            continue
        scope_rank = 0 if rule.get("project_id") is not None else 1
        specificity = _specificity_score(rule)
        priority = int(rule.get("priority", 99999))
        confidence_base = float(rule.get("confidence_base", 0.0))
        created_at = str(rule.get("created_at", ""))
        rule_id = str(rule.get("id", ""))
        ranked.append((scope_rank, -specificity, priority, -confidence_base, created_at, rule_id, rule))

    if not ranked:
        return None

    ranked.sort(key=lambda x: x[:-1])
    return ranked[0][-1]


def auto_assign_task(
    *,
    task_id: str,
    trace_id: str,
    store: TicketingStore,
    confidence_threshold: float = 0.75,
    now: datetime | None = None,
) -> dict:
    ensure_store_defaults(store)
    ts = now or datetime.now(timezone.utc)
    task = store.tasks_by_id.get(task_id)
    if not task:
        raise Stage1BRequestError(404, "not_found", "task not found")

    candidates = list(store.routing_rules_by_id.values())
    winner = select_best_rule(task, candidates)
    if not winner:
        task["routing_decision"] = "manual_queue"
        task["routing_reason"] = "NO_MATCH"
        task["routing_rule_id"] = None
        task["routing_confidence"] = 0.0
        task["updated_at"] = ts.isoformat()
        return {"status": "MANUAL_QUEUE", "reason": "NO_MATCH", "confidence": 0.0}

    confidence = _compute_confidence(winner)
    if confidence < confidence_threshold:
        task["routing_decision"] = "manual_queue"
        task["routing_reason"] = "LOW_CONFIDENCE"
        task["routing_rule_id"] = winner["id"]
        task["routing_confidence"] = confidence
        task["updated_at"] = ts.isoformat()
        return {
            "status": "MANUAL_QUEUE",
            "reason": "LOW_CONFIDENCE",
            "confidence": confidence,
            "rule_id": winner["id"],
        }

    assignee_id = winner.get("assignee_user_id")
    if not assignee_id:
        task["routing_decision"] = "manual_queue"
        task["routing_reason"] = "NO_USER_ASSIGNEE"
        task["routing_rule_id"] = winner["id"]
        task["routing_confidence"] = confidence
        task["updated_at"] = ts.isoformat()
        return {
            "status": "MANUAL_QUEUE",
            "reason": "NO_USER_ASSIGNEE",
            "confidence": confidence,
            "rule_id": winner["id"],
        }

    task["assignee_user_id"] = assignee_id
    task["auto_assigned"] = True
    task["assignment_confidence"] = confidence
    task["routing_rule_id"] = winner["id"]
    task["routing_confidence"] = confidence
    task["routing_decision"] = "assigned"
    task["routing_reason"] = "RULE_MATCH"
    if task.get("first_assigned_at") is None:
        task["first_assigned_at"] = ts.isoformat()
    task["updated_at"] = ts.isoformat()

    idempotency_key = f"task:{task_id}:task.auto_assigned:v1"
    event = _event_envelope(
        event_type="task.auto_assigned",
        aggregate_type="task",
        aggregate_id=task_id,
        organization_id=task["organization_id"],
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        payload={
            "task_id": task_id,
            "assignee_id": assignee_id,
            "rule_id": winner["id"],
            "confidence": confidence,
            "assignment_mode": "rule_based",
        },
        occurred_at=ts,
    )
    append_outbox_event(store, event)

    return {
        "status": "ASSIGNED",
        "task_id": task_id,
        "assignee_id": assignee_id,
        "rule_id": winner["id"],
        "confidence": confidence,
    }


def create_escalation(
    *,
    task_id: str,
    policy: dict,
    store: TicketingStore,
    now: datetime | None = None,
) -> dict:
    ensure_store_defaults(store)
    ts = now or datetime.now(timezone.utc)
    task = store.tasks_by_id.get(task_id)
    if not task:
        raise Stage1BRequestError(404, "not_found", "task not found")
    if not task.get("assignee_user_id"):
        raise Stage1BRequestError(422, "validation_error", "task must be assigned before escalation timer starts")

    ack_minutes_l1 = int(policy.get("ack_minutes_l1", 120))
    existing = store.assignment_escalations_by_task_id.get(task_id)
    if existing and existing.get("status") in {"OPEN", "ESCALATED"}:
        return existing

    escalation = {
        "id": str(uuid.uuid4()),
        "organization_id": task["organization_id"],
        "project_id": task["project_id"],
        "task_id": task_id,
        "policy_id": str(policy["id"]),
        "max_levels": int(policy.get("max_levels", 3)),
        "current_level": 1,
        "assigned_at": ts.isoformat(),
        "ack_due_at": (ts + timedelta(minutes=ack_minutes_l1)).isoformat(),
        "next_escalation_at": (ts + timedelta(minutes=ack_minutes_l1)).isoformat(),
        "last_notified_at": None,
        "status": "OPEN",
    }
    store.assignment_escalations_by_task_id[task_id] = escalation
    return escalation


def process_overdue_assignments(
    *,
    trace_id: str,
    store: TicketingStore,
    now: datetime | None = None,
) -> list[dict]:
    ensure_store_defaults(store)
    ts = now or datetime.now(timezone.utc)
    emitted: list[dict] = []

    for task_id, escalation in list(store.assignment_escalations_by_task_id.items()):
        if escalation["status"] not in {"OPEN", "ESCALATED"}:
            continue
        next_escalation_at = _as_dt(escalation.get("next_escalation_at"))
        if next_escalation_at is None or next_escalation_at > ts:
            continue

        last_notified = _as_dt(escalation.get("last_notified_at"))
        if last_notified is not None and (ts - last_notified) < timedelta(minutes=30):
            continue

        if escalation["current_level"] < escalation["max_levels"]:
            escalation["current_level"] += 1
        escalation["status"] = "ESCALATED"
        escalation["last_notified_at"] = ts.isoformat()

        ack_due_at = _as_dt(escalation.get("ack_due_at")) or ts
        overdue_by_hours = max(0, int((ts - ack_due_at).total_seconds() // 3600))
        task = store.tasks_by_id[task_id]
        event = _event_envelope(
            event_type="task.assignment_overdue",
            aggregate_type="task",
            aggregate_id=task_id,
            organization_id=task["organization_id"],
            idempotency_key=f"task:{task_id}:task.assignment_overdue:l{escalation['current_level']}",
            trace_id=trace_id,
            payload={
                "task_id": task_id,
                "assignee_id": task.get("assignee_user_id"),
                "overdue_by_hours": overdue_by_hours,
                "escalation_level": escalation["current_level"],
                "policy_id": escalation["policy_id"],
            },
            occurred_at=ts,
        )
        if append_outbox_event(store, event):
            emitted.append(event)

        if escalation["current_level"] >= escalation["max_levels"]:
            escalation["next_escalation_at"] = None
        else:
            escalation["next_escalation_at"] = (ts + timedelta(hours=1)).isoformat()

    return emitted
