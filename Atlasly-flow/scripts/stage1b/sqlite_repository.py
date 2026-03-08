from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from scripts.stage1b.notification_policy import NotificationStore
from scripts.stage1b.repositories import notification_store_from_dict
from scripts.stage1b.repositories import notification_store_to_dict
from scripts.stage1b.repositories import ticket_store_from_dict
from scripts.stage1b.repositories import ticket_store_to_dict
from scripts.stage1b.ticketing_service import TicketingStore


class Stage1BSQLiteRepository:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS stage1b_state (
              state_key TEXT PRIMARY KEY,
              state_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _encode(value: dict) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _decode(value: str | None) -> dict | None:
        if not value:
            return None
        return json.loads(value)

    def _get_state(self, key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT state_json FROM stage1b_state WHERE state_key = ?",
            (key,),
        ).fetchone()
        return self._decode(row["state_json"] if row else None)

    def _set_state(self, key: str, payload: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO stage1b_state(state_key, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
              state_json = excluded.state_json,
              updated_at = excluded.updated_at
            """,
            (key, self._encode(payload), self._now_iso()),
        )
        self.conn.commit()

    def load_ticket_store(self) -> TicketingStore:
        payload = self._get_state("ticket_store")
        return ticket_store_from_dict(payload)

    def save_ticket_store(self, store: TicketingStore) -> None:
        self._set_state("ticket_store", ticket_store_to_dict(store))

    def load_notification_store(self) -> NotificationStore:
        payload = self._get_state("notification_store")
        return notification_store_from_dict(payload)

    def save_notification_store(self, store: NotificationStore) -> None:
        self._set_state("notification_store", notification_store_to_dict(store))
