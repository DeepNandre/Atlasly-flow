from __future__ import annotations

from datetime import datetime, timezone
import pickle
import sqlite3


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStateSQLiteStore:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def _create_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state_snapshots (
              state_key TEXT PRIMARY KEY,
              payload BLOB NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def load(self, *, state_key: str) -> object | None:
        row = self.conn.execute(
            "SELECT payload FROM runtime_state_snapshots WHERE state_key = ?",
            (state_key,),
        ).fetchone()
        if row is None:
            return None
        return pickle.loads(row["payload"])

    def save(self, *, state_key: str, payload: object) -> None:
        blob = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO runtime_state_snapshots (state_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                  payload = excluded.payload,
                  updated_at = excluded.updated_at
                """,
                (state_key, blob, _iso_now()),
            )

    def delete(self, *, state_key: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM runtime_state_snapshots WHERE state_key = ?",
                (state_key,),
            )
