from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from scripts.stage1b.ticketing_service import TicketingStore


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def compute_routing_quality(store: TicketingStore) -> dict[str, float | int]:
    auto_tasks = [t for t in store.tasks_by_id.values() if t.get("auto_assigned")]
    if not auto_tasks:
        return {"auto_assignment_success_rate": 0.0, "auto_assigned_total": 0, "manual_override_count": 0}

    feedback_by_task = {f["task_id"] for f in store.task_feedback_by_id.values()}
    overrides = 0
    for task in auto_tasks:
        if task["id"] in feedback_by_task:
            overrides += 1

    success_rate = (len(auto_tasks) - overrides) / len(auto_tasks)
    return {
        "auto_assignment_success_rate": round(success_rate, 4),
        "auto_assigned_total": len(auto_tasks),
        "manual_override_count": overrides,
    }


def compute_triage_velocity(store: TicketingStore, letter_id: str) -> dict[str, float | None]:
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        return {"median_minutes_to_first_assignment": None, "minutes_to_fully_assigned": None}

    approved_at = _parse_iso(letter.get("approved_at")) or _parse_iso(letter.get("completed_at"))
    if approved_at is None:
        return {"median_minutes_to_first_assignment": None, "minutes_to_fully_assigned": None}

    relevant_tasks = [t for t in store.tasks_by_id.values() if t.get("project_id") == letter.get("project_id")]
    assignment_minutes: list[float] = []
    for task in relevant_tasks:
        first_assigned = _parse_iso(task.get("first_assigned_at"))
        if first_assigned is None:
            continue
        assignment_minutes.append((first_assigned - approved_at).total_seconds() / 60.0)

    if not assignment_minutes:
        return {"median_minutes_to_first_assignment": None, "minutes_to_fully_assigned": None}

    return {
        "median_minutes_to_first_assignment": round(float(median(assignment_minutes)), 2),
        "minutes_to_fully_assigned": round(float(max(assignment_minutes)), 2),
    }


def compute_operability(store: TicketingStore) -> dict[str, float | int]:
    replay_ratio = 0.0
    if store.generation_request_count > 0:
        replay_ratio = store.generation_replay_count / store.generation_request_count

    overdue_events = [e for e in store.outbox_events if e.get("event_type") == "task.assignment_overdue"]
    return {
        "generation_request_count": store.generation_request_count,
        "generation_replay_count": store.generation_replay_count,
        "generation_replay_ratio": round(replay_ratio, 4),
        "duplicate_prevented_count": store.duplicate_prevented_count,
        "overdue_event_count": len(overdue_events),
    }
