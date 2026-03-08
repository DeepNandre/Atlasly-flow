from __future__ import annotations


def dispatch_pending_outbox_events(*, repository, max_events: int = 100) -> dict:
    pending = repository.list_outbox_events(publish_state="pending", limit=max_events)
    published_ids: list[str] = []
    for event in pending:
        repository.mark_outbox_event_published(event["event_id"])
        published_ids.append(event["event_id"])
    return {
        "pending_count": len(pending),
        "published_count": len(published_ids),
        "published_event_ids": published_ids,
    }
