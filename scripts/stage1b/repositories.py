from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import copy
from typing import Protocol

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.ticketing_service import TicketingStore
from scripts.stage1b.ticketing_service import ensure_store_defaults


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def ticket_store_to_dict(store: TicketingStore) -> dict:
    ensure_store_defaults(store)
    payload = asdict(store)
    payload["task_id_by_org_extraction"] = {
        f"{org}|{extraction}": task_id
        for (org, extraction), task_id in store.task_id_by_org_extraction.items()
    }
    payload["generation_runs_by_org_key"] = {
        f"{org}|{idem}": run
        for (org, idem), run in store.generation_runs_by_org_key.items()
    }
    payload["outbox_event_keys"] = sorted(list(store.outbox_event_keys))
    return payload


def ticket_store_from_dict(payload: dict | None) -> TicketingStore:
    if not payload:
        return TicketingStore.empty()

    store = TicketingStore(
        letters_by_id=dict(payload.get("letters_by_id", {})),
        extractions_by_id=dict(payload.get("extractions_by_id", {})),
        tasks_by_id=dict(payload.get("tasks_by_id", {})),
        task_id_by_org_extraction={
            tuple(k.split("|", 1)): v
            for k, v in payload.get("task_id_by_org_extraction", {}).items()
        }
        if all(isinstance(k, str) for k in payload.get("task_id_by_org_extraction", {}).keys())
        else dict(payload.get("task_id_by_org_extraction", {})),
        generation_runs_by_org_key={
            tuple(k.split("|", 1)): v
            for k, v in payload.get("generation_runs_by_org_key", {}).items()
        }
        if all(isinstance(k, str) for k in payload.get("generation_runs_by_org_key", {}).keys())
        else dict(payload.get("generation_runs_by_org_key", {})),
        task_feedback_by_id=dict(payload.get("task_feedback_by_id", {})),
        routing_rules_by_id=dict(payload.get("routing_rules_by_id", {})),
        assignment_escalations_by_task_id=dict(payload.get("assignment_escalations_by_task_id", {})),
        manual_queue_by_task_id=dict(payload.get("manual_queue_by_task_id", {})),
        generation_request_count=int(payload.get("generation_request_count", 0)),
        generation_replay_count=int(payload.get("generation_replay_count", 0)),
        duplicate_prevented_count=int(payload.get("duplicate_prevented_count", 0)),
        outbox_event_keys=set(payload.get("outbox_event_keys", [])),
        outbox_events=list(payload.get("outbox_events", [])),
        overdue_ticks_by_key=dict(payload.get("overdue_ticks_by_key", {})),
    )
    ensure_store_defaults(store)
    return store


def notification_store_to_dict(store: NotificationStore) -> dict:
    return {
        "queued_digest_items": copy.deepcopy(store.queued_digest_items),
        "sent_notifications": copy.deepcopy(store.sent_notifications),
        "last_sent_by_dedupe": {
            key: _iso(ts) if isinstance(ts, datetime) else str(ts)
            for key, ts in store.last_sent_by_dedupe.items()
        },
    }


def notification_store_from_dict(payload: dict | None) -> NotificationStore:
    if not payload:
        return NotificationStore.empty()
    return NotificationStore(
        queued_digest_items=list(payload.get("queued_digest_items", [])),
        sent_notifications=list(payload.get("sent_notifications", [])),
        last_sent_by_dedupe={
            key: _parse_iso(str(raw))
            for key, raw in payload.get("last_sent_by_dedupe", {}).items()
        },
    )


class Stage1BRepository(Protocol):
    def load_ticket_store(self) -> TicketingStore:
        ...

    def save_ticket_store(self, store: TicketingStore) -> None:
        ...

    def load_notification_store(self) -> NotificationStore:
        ...

    def save_notification_store(self, store: NotificationStore) -> None:
        ...


class Stage1BInMemoryRepository:
    def __init__(self):
        self._ticket_store = TicketingStore.empty()
        self._notification_store = NotificationStore.empty()

    def load_ticket_store(self) -> TicketingStore:
        # Deep-copy boundary to simulate process-level isolation.
        return ticket_store_from_dict(ticket_store_to_dict(self._ticket_store))

    def save_ticket_store(self, store: TicketingStore) -> None:
        self._ticket_store = ticket_store_from_dict(ticket_store_to_dict(store))

    def load_notification_store(self) -> NotificationStore:
        return notification_store_from_dict(notification_store_to_dict(self._notification_store))

    def save_notification_store(self, store: NotificationStore) -> None:
        self._notification_store = notification_store_from_dict(notification_store_to_dict(store))
