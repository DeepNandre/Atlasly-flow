from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


IMMEDIATE_EVENT_TYPES = {
    "task.auto_assigned",
    "task.reassigned",
    "task.assignment_overdue",
}

DIGEST_EVENT_TYPES = {
    "task.assignment_due_soon",
    "task.manual_queue_entered",
    "routing.rule_updated",
}


@dataclass
class NotificationStore:
    queued_digest_items: list[dict]
    sent_notifications: list[dict]
    last_sent_by_dedupe: dict[str, datetime]

    @classmethod
    def empty(cls) -> "NotificationStore":
        return cls(queued_digest_items=[], sent_notifications=[], last_sent_by_dedupe={})


def build_dedupe_key(event: dict, user_id: str) -> str:
    payload = event.get("payload", {})
    task_id = payload.get("task_id", event.get("aggregate_id", "unknown"))
    level = payload.get("escalation_level", 0)
    return f"{task_id}:{event['event_type']}:{level}:{user_id}"


def classify_event_delivery(event_type: str, user_mode: str) -> str:
    """
    Returns one of: immediate, digest, suppress
    user_mode:
      - immediate: receive immediate and escalation notices
      - digest: non-critical events digested; escalation immediate
      - escalation_only: only escalation events immediate
    """
    if user_mode == "escalation_only":
        return "immediate" if event_type == "task.assignment_overdue" else "suppress"

    if event_type in IMMEDIATE_EVENT_TYPES:
        if user_mode == "digest" and event_type != "task.assignment_overdue":
            return "digest"
        return "immediate"

    if event_type in DIGEST_EVENT_TYPES:
        return "digest"

    return "suppress"


def process_notification_event(
    *,
    event: dict,
    user_id: str,
    user_mode: str,
    notification_store: NotificationStore,
    now: datetime | None = None,
    suppression_minutes: int = 30,
) -> str:
    ts = now or datetime.now(timezone.utc)
    delivery = classify_event_delivery(event["event_type"], user_mode=user_mode)
    if delivery == "suppress":
        return "suppressed"

    dedupe_key = build_dedupe_key(event, user_id)
    last_sent = notification_store.last_sent_by_dedupe.get(dedupe_key)
    if delivery == "immediate" and last_sent and ts - last_sent < timedelta(minutes=suppression_minutes):
        return "suppressed"

    if delivery == "digest":
        notification_store.queued_digest_items.append(
            {
                "user_id": user_id,
                "event_type": event["event_type"],
                "event_id": event.get("event_id"),
                "dedupe_key": dedupe_key,
                "queued_at": ts.isoformat(),
                "payload": event.get("payload", {}),
            }
        )
        return "digest_queued"

    notification_store.sent_notifications.append(
        {
            "user_id": user_id,
            "event_type": event["event_type"],
            "event_id": event.get("event_id"),
            "dedupe_key": dedupe_key,
            "sent_at": ts.isoformat(),
        }
    )
    notification_store.last_sent_by_dedupe[dedupe_key] = ts
    return "sent_immediate"
