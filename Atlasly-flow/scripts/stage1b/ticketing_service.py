from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from scripts.stage1b.tasking_api import Stage1BRequestError
from scripts.stage1b.tasking_api import evaluate_idempotent_replay
from scripts.stage1b.tasking_api import parse_create_tasks_request
from scripts.stage1b.tasking_api import validate_reassignment_payload

TASK_WRITE_ROLES = {"owner", "admin", "pm", "reviewer"}


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    user_id: str
    requester_role: str


@dataclass
class TicketingStore:
    letters_by_id: dict[str, dict]
    extractions_by_id: dict[str, dict]
    tasks_by_id: dict[str, dict]
    task_id_by_org_extraction: dict[tuple[str, str], str]
    generation_runs_by_org_key: dict[tuple[str, str], dict]
    task_feedback_by_id: dict[str, dict]
    routing_rules_by_id: dict[str, dict]
    assignment_escalations_by_task_id: dict[str, dict]
    manual_queue_by_task_id: dict[str, dict]
    generation_request_count: int
    generation_replay_count: int
    duplicate_prevented_count: int
    outbox_event_keys: set[str]
    outbox_events: list[dict]
    overdue_ticks_by_key: dict[str, dict]

    @classmethod
    def empty(cls) -> "TicketingStore":
        return cls(
            letters_by_id={},
            extractions_by_id={},
            tasks_by_id={},
            task_id_by_org_extraction={},
            generation_runs_by_org_key={},
            task_feedback_by_id={},
            routing_rules_by_id={},
            assignment_escalations_by_task_id={},
            manual_queue_by_task_id={},
            generation_request_count=0,
            generation_replay_count=0,
            duplicate_prevented_count=0,
            outbox_event_keys=set(),
            outbox_events=[],
            overdue_ticks_by_key={},
        )


def ensure_store_defaults(store: TicketingStore) -> None:
    if getattr(store, "manual_queue_by_task_id", None) is None:
        store.manual_queue_by_task_id = {}
    if getattr(store, "generation_request_count", None) is None:
        store.generation_request_count = 0
    if getattr(store, "generation_replay_count", None) is None:
        store.generation_replay_count = 0
    if getattr(store, "duplicate_prevented_count", None) is None:
        store.duplicate_prevented_count = 0
    if getattr(store, "outbox_event_keys", None) is None:
        store.outbox_event_keys = set()
    if getattr(store, "overdue_ticks_by_key", None) is None:
        store.overdue_ticks_by_key = {}


def append_outbox_event(store: TicketingStore, event: dict) -> bool:
    """
    Appends only once per stable event key to keep retries/replays deterministic.
    Returns True when appended, False when deduped.
    """
    ensure_store_defaults(store)
    key = f"{event.get('organization_id','')}|{event.get('event_type','')}|{event.get('idempotency_key','')}"
    if key in store.outbox_event_keys:
        return False
    store.outbox_event_keys.add(key)
    store.outbox_events.append(event)
    return True


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
        "produced_by": "ticketing-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def create_tasks_from_approved_extractions(
    *,
    letter_id: str,
    request_body: dict[str, object] | None,
    idempotency_key: str | None,
    trace_id: str,
    auth_context: AuthContext,
    store: TicketingStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ensure_store_defaults(store)
    ts = now or datetime.now(timezone.utc)
    store.generation_request_count += 1
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1BRequestError(404, "not_found", "comment letter not found")

    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1BRequestError(403, "forbidden", "letter belongs to another organization")

    if auth_context.requester_role not in TASK_WRITE_ROLES:
        raise Stage1BRequestError(403, "forbidden", "role cannot create tasks")

    parsed = parse_create_tasks_request(
        organization_id=letter["organization_id"],
        project_id=letter["project_id"],
        letter_id=letter_id,
        body=request_body,
        client_idempotency_key=idempotency_key,
        letter_version_hash=letter.get("version_hash", "unknown"),
    )

    run_key = (auth_context.organization_id, parsed.idempotency_key)
    existing_run = store.generation_runs_by_org_key.get(run_key)
    status, outcome = evaluate_idempotent_replay(
        existing_run_status=None if not existing_run else existing_run["status"],
        existing_request_hash=None if not existing_run else existing_run["request_hash"],
        incoming_request_hash=parsed.request_hash,
    )
    if outcome == "replay":
        store.generation_replay_count += 1
        return 200, existing_run["response"]
    if outcome == "conflict":
        raise Stage1BRequestError(409, "idempotency_conflict", "idempotency key reused with different request")

    created_task_ids: list[str] = []
    existing_task_ids: list[str] = []

    for extraction_id in parsed.approved_extraction_ids:
        extraction = store.extractions_by_id.get(extraction_id)
        if not extraction:
            raise Stage1BRequestError(422, "validation_error", f"approved_extraction_id {extraction_id} not found")
        if extraction["letter_id"] != letter_id:
            raise Stage1BRequestError(422, "validation_error", "extraction does not belong to requested letter")
        if extraction["status"] != "approved_snapshot":
            raise Stage1BRequestError(422, "validation_error", "extraction is not approved_snapshot")

        dedupe_key = (auth_context.organization_id, extraction_id)
        existing_task_id = store.task_id_by_org_extraction.get(dedupe_key)
        if existing_task_id:
            existing_task_ids.append(existing_task_id)
            continue

        task_id = str(uuid.uuid4())
        store.tasks_by_id[task_id] = {
            "id": task_id,
            "organization_id": auth_context.organization_id,
            "project_id": letter["project_id"],
            "source_extraction_id": extraction_id,
            "title": f"Resolve extraction {extraction['comment_id']}",
            "discipline": extraction.get("discipline"),
            "status": "todo",
            "auto_assigned": False,
            "assignment_confidence": None,
            "assignee_user_id": None,
            "first_assigned_at": None,
            "created_at": ts.isoformat(),
            "updated_at": ts.isoformat(),
        }
        store.task_id_by_org_extraction[dedupe_key] = task_id
        created_task_ids.append(task_id)

    response = {
        "letter_id": letter_id,
        "created_count": len(created_task_ids),
        "existing_count": len(existing_task_ids),
        "task_ids": created_task_ids + existing_task_ids,
        "idempotency_key": parsed.idempotency_key,
        "run_status": "COMPLETED",
    }
    store.duplicate_prevented_count += len(existing_task_ids)
    store.generation_runs_by_org_key[run_key] = {
        "organization_id": auth_context.organization_id,
        "project_id": letter["project_id"],
        "letter_id": letter_id,
        "status": "COMPLETED",
        "request_hash": parsed.request_hash,
        "response": response,
        "created_at": ts.isoformat(),
    }

    event = _event_envelope(
        event_type="tasks.bulk_created_from_extractions",
        aggregate_type="comment_letter",
        aggregate_id=letter_id,
        organization_id=auth_context.organization_id,
        idempotency_key=f"{parsed.idempotency_key}:tasks.bulk_created_from_extractions:v1",
        trace_id=trace_id,
        payload={
            "letter_id": letter_id,
            "project_id": letter["project_id"],
            "task_ids": response["task_ids"],
            "created_count": response["created_count"],
            "existing_count": response["existing_count"],
        },
        occurred_at=ts,
    )
    append_outbox_event(store, event)
    return 201, response


def reassign_task(
    *,
    task_id: str,
    payload: dict[str, object],
    auth_context: AuthContext,
    store: TicketingStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ensure_store_defaults(store)
    ts = now or datetime.now(timezone.utc)
    task = store.tasks_by_id.get(task_id)
    if not task:
        raise Stage1BRequestError(404, "not_found", "task not found")

    if task["organization_id"] != auth_context.organization_id:
        raise Stage1BRequestError(403, "forbidden", "task belongs to another organization")

    if auth_context.requester_role not in TASK_WRITE_ROLES:
        raise Stage1BRequestError(403, "forbidden", "role cannot reassign tasks")

    validate_reassignment_payload(payload)
    from_assignee = str(payload["from_assignee_id"])
    if task.get("assignee_user_id") != from_assignee:
        raise Stage1BRequestError(422, "validation_error", "from_assignee_id must match current assignee")

    task["assignee_user_id"] = str(payload["to_assignee_id"])
    task["updated_at"] = ts.isoformat()

    feedback_id = str(uuid.uuid4())
    feedback = {
        "id": feedback_id,
        "organization_id": auth_context.organization_id,
        "project_id": task["project_id"],
        "task_id": task_id,
        "from_assignee_id": from_assignee,
        "to_assignee_id": str(payload["to_assignee_id"]),
        "source_rule_id": payload.get("source_rule_id"),
        "source_confidence": payload.get("source_confidence"),
        "feedback_reason_code": str(payload["feedback_reason_code"]),
        "feedback_subreason": payload.get("feedback_subreason"),
        "actor_user_id": auth_context.user_id,
        "was_auto_assigned": bool(task.get("auto_assigned", False)),
        "created_at": ts.isoformat(),
    }
    store.task_feedback_by_id[feedback_id] = feedback

    return 200, {
        "task_id": task_id,
        "from_assignee_id": from_assignee,
        "to_assignee_id": task["assignee_user_id"],
        "feedback_id": feedback_id,
    }
