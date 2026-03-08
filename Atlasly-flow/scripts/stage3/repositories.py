from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass
class Stage3PersistenceStore:
    preflight_scores: dict[str, dict]
    payout_instructions: dict[str, dict]
    payout_by_idempotency: dict[tuple[str, str], str]
    financial_events: dict[str, dict]
    reconciliation_runs: dict[str, dict]
    outbox_events: dict[str, dict]

    @classmethod
    def empty(cls) -> "Stage3PersistenceStore":
        return cls({}, {}, {}, {}, {}, {})


class Stage3Repository:
    def __init__(self, store: Stage3PersistenceStore):
        self._store = store

    def insert_preflight_score(self, score_record: dict) -> dict:
        record = dict(score_record)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        self._store.preflight_scores[record["id"]] = record
        return record

    def create_or_get_payout_instruction(self, *, organization_id: str, idempotency_key: str, instruction: dict) -> tuple[bool, dict]:
        idem_key = (organization_id, idempotency_key)
        existing_id = self._store.payout_by_idempotency.get(idem_key)
        if existing_id:
            return False, self._store.payout_instructions[existing_id]

        record = dict(instruction)
        record.setdefault("instruction_id", str(uuid.uuid4()))
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record.setdefault("updated_at", record["created_at"])
        self._store.payout_instructions[record["instruction_id"]] = record
        self._store.payout_by_idempotency[idem_key] = record["instruction_id"]
        return True, record

    def create_instruction_with_outbox(
        self,
        *,
        organization_id: str,
        idempotency_key: str,
        instruction: dict,
        event: dict,
    ) -> tuple[bool, dict]:
        created, record = self.create_or_get_payout_instruction(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            instruction=instruction,
        )
        if not created:
            return False, record
        self.insert_outbox_event(event)
        return True, record

    def get_payout_instruction(self, *, organization_id: str, instruction_id: str) -> dict | None:
        record = self._store.payout_instructions.get(instruction_id)
        if not record:
            return None
        if record.get("organization_id") != organization_id:
            return None
        return record

    def update_payout_instruction_state(
        self, *, organization_id: str, instruction_id: str, new_state: str, updated_at: str
    ) -> dict:
        record = self._store.payout_instructions.get(instruction_id)
        if not record or record.get("organization_id") != organization_id:
            raise KeyError("instruction not found")
        record["instruction_state"] = new_state
        record["updated_at"] = updated_at
        return record

    def append_financial_event(self, event: dict) -> dict:
        record = dict(event)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        self._store.financial_events[record["id"]] = record
        return record

    def list_financial_events_by_org(self, organization_id: str) -> list[dict]:
        return [e for e in self._store.financial_events.values() if e["organization_id"] == organization_id]

    def save_reconciliation_run(self, run: dict) -> dict:
        record = dict(run)
        record.setdefault("id", str(uuid.uuid4()))
        self._store.reconciliation_runs[record["id"]] = record
        return record

    def get_reconciliation_run(self, run_id: str) -> dict | None:
        return self._store.reconciliation_runs.get(run_id)

    def insert_outbox_event(self, event: dict) -> dict:
        record = dict(event)
        record.setdefault("event_id", str(uuid.uuid4()))
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record.setdefault("publish_state", "pending")
        record.setdefault("publish_attempts", 0)
        self._store.outbox_events[record["event_id"]] = record
        return record

    def list_outbox_events(self, *, publish_state: str | None = "pending", limit: int = 100) -> list[dict]:
        if publish_state is None:
            events = list(self._store.outbox_events.values())
        else:
            events = [
                e for e in self._store.outbox_events.values() if e.get("publish_state", "pending") == publish_state
            ]
        events.sort(key=lambda item: item.get("created_at", ""))
        return events[:limit]

    def mark_outbox_event_published(self, event_id: str) -> dict:
        record = self._store.outbox_events.get(event_id)
        if not record:
            raise KeyError("event not found")
        record["publish_state"] = "published"
        record["published_at"] = datetime.now(timezone.utc).isoformat()
        return record
