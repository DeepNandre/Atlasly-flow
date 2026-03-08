from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid


class Stage3SQLiteRepository:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS preflight_scores (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              permit_id TEXT,
              ahj_id TEXT NOT NULL,
              permit_type TEXT NOT NULL,
              score REAL NOT NULL,
              band TEXT NOT NULL,
              confidence_score REAL NOT NULL,
              model_version TEXT NOT NULL,
              scored_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payout_instructions (
              instruction_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              milestone_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              beneficiary_id TEXT NOT NULL,
              amount REAL NOT NULL,
              currency TEXT NOT NULL,
              provider TEXT NOT NULL,
              instruction_state TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (organization_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS financial_events (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              instruction_id TEXT,
              milestone_id TEXT,
              event_type TEXT NOT NULL,
              amount REAL NOT NULL,
              currency TEXT,
              trace_id TEXT,
              source_service TEXT NOT NULL,
              payload TEXT NOT NULL,
              occurred_at TEXT NOT NULL,
              recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reconciliation_runs (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              provider TEXT NOT NULL,
              run_started_at TEXT NOT NULL,
              run_finished_at TEXT,
              run_status TEXT NOT NULL,
              matched_count INTEGER NOT NULL,
              mismatched_count INTEGER NOT NULL,
              missing_internal_count INTEGER NOT NULL,
              missing_provider_count INTEGER NOT NULL,
              result_payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stage3_event_outbox (
              event_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              event_version INTEGER NOT NULL,
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              trace_id TEXT NOT NULL,
              payload TEXT NOT NULL,
              occurred_at TEXT NOT NULL,
              produced_by TEXT NOT NULL,
              publish_state TEXT NOT NULL DEFAULT 'pending',
              publish_attempts INTEGER NOT NULL DEFAULT 0,
              published_at TEXT,
              created_at TEXT NOT NULL,
              UNIQUE (organization_id, idempotency_key, event_type)
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        out = dict(row)
        for key in ("payload", "result_payload"):
            if key in out and isinstance(out[key], str):
                out[key] = json.loads(out[key])
        return out

    def count_rows(self, table_name: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table_name}").fetchone()
        return int(row["c"])

    def insert_preflight_score(self, score_record: dict) -> dict:
        record = dict(score_record)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self.conn.execute(
            """
            INSERT INTO preflight_scores (
              id, organization_id, project_id, permit_id, ahj_id, permit_type,
              score, band, confidence_score, model_version, scored_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["organization_id"],
                record["project_id"],
                record.get("permit_id"),
                record["ahj_id"],
                record["permit_type"],
                record["score"],
                record["band"],
                record["confidence_score"],
                record["model_version"],
                record["scored_at"],
                record["created_at"],
            ),
        )
        self.conn.commit()
        return record

    def create_or_get_payout_instruction(
        self, *, organization_id: str, idempotency_key: str, instruction: dict
    ) -> tuple[bool, dict]:
        existing = self.conn.execute(
            """
            SELECT * FROM payout_instructions
            WHERE organization_id = ? AND idempotency_key = ?
            """,
            (organization_id, idempotency_key),
        ).fetchone()
        if existing:
            return False, dict(existing)

        record = dict(instruction)
        record.setdefault("instruction_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        record.setdefault("updated_at", record["created_at"])
        self.conn.execute(
            """
            INSERT INTO payout_instructions (
              instruction_id, organization_id, milestone_id, permit_id, project_id,
              beneficiary_id, amount, currency, provider, instruction_state,
              idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["instruction_id"],
                record["organization_id"],
                record["milestone_id"],
                record["permit_id"],
                record["project_id"],
                record["beneficiary_id"],
                record["amount"],
                record["currency"],
                record["provider"],
                record["instruction_state"],
                record["idempotency_key"],
                record["created_at"],
                record["updated_at"],
            ),
        )
        self.conn.commit()
        return True, record

    def get_payout_instruction(self, *, organization_id: str, instruction_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM payout_instructions
            WHERE organization_id = ? AND instruction_id = ?
            """,
            (organization_id, instruction_id),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def list_payout_instructions_by_org(self, *, organization_id: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM payout_instructions
            WHERE organization_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (organization_id, max(1, int(limit))),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_payout_instruction_state(
        self, *, organization_id: str, instruction_id: str, new_state: str, updated_at: str
    ) -> dict:
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE payout_instructions
                SET instruction_state = ?, updated_at = ?
                WHERE organization_id = ? AND instruction_id = ?
                """,
                (new_state, updated_at, organization_id, instruction_id),
            )
            if cur.rowcount == 0:
                raise KeyError("instruction not found")
        record = self.get_payout_instruction(organization_id=organization_id, instruction_id=instruction_id)
        if not record:
            raise KeyError("instruction not found")
        return record

    def create_instruction_with_outbox(
        self, *, organization_id: str, idempotency_key: str, instruction: dict, event: dict
    ) -> tuple[bool, dict]:
        with self.conn:
            existing = self.conn.execute(
                """
                SELECT * FROM payout_instructions
                WHERE organization_id = ? AND idempotency_key = ?
                """,
                (organization_id, idempotency_key),
            ).fetchone()
            if existing:
                return False, dict(existing)

            record = dict(instruction)
            record.setdefault("instruction_id", str(uuid.uuid4()))
            record.setdefault("created_at", self._now_iso())
            record.setdefault("updated_at", record["created_at"])

            self.conn.execute(
                """
                INSERT INTO payout_instructions (
                  instruction_id, organization_id, milestone_id, permit_id, project_id,
                  beneficiary_id, amount, currency, provider, instruction_state,
                  idempotency_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["instruction_id"],
                    record["organization_id"],
                    record["milestone_id"],
                    record["permit_id"],
                    record["project_id"],
                    record["beneficiary_id"],
                    record["amount"],
                    record["currency"],
                    record["provider"],
                    record["instruction_state"],
                    record["idempotency_key"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )

            outbox = dict(event)
            outbox.setdefault("event_id", str(uuid.uuid4()))
            outbox.setdefault("created_at", self._now_iso())
            self.conn.execute(
                """
                INSERT INTO stage3_event_outbox (
                  event_id, organization_id, event_type, event_version, aggregate_type,
                  aggregate_id, idempotency_key, trace_id, payload, occurred_at,
                  produced_by, publish_state, publish_attempts, published_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outbox["event_id"],
                    outbox["organization_id"],
                    outbox["event_type"],
                    outbox["event_version"],
                    outbox["aggregate_type"],
                    outbox["aggregate_id"],
                    outbox["idempotency_key"],
                    outbox["trace_id"],
                    self._json(outbox["payload"]),
                    outbox["occurred_at"],
                    outbox["produced_by"],
                    outbox.get("publish_state", "pending"),
                    int(outbox.get("publish_attempts", 0)),
                    outbox.get("published_at"),
                    outbox["created_at"],
                ),
            )
            return True, record

    def append_financial_event(self, event: dict) -> dict:
        record = dict(event)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("recorded_at", self._now_iso())
        self.conn.execute(
            """
            INSERT INTO financial_events (
              id, organization_id, instruction_id, milestone_id, event_type, amount,
              currency, trace_id, source_service, payload, occurred_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["organization_id"],
                record.get("instruction_id"),
                record.get("milestone_id"),
                record["event_type"],
                record["amount"],
                record.get("currency"),
                record.get("trace_id"),
                record["source_service"],
                self._json(record.get("payload", {})),
                record["occurred_at"],
                record["recorded_at"],
            ),
        )
        self.conn.commit()
        return record

    def list_financial_events_by_org(self, organization_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM financial_events WHERE organization_id = ? ORDER BY occurred_at ASC",
            (organization_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def save_reconciliation_run(self, run: dict) -> dict:
        record = dict(run)
        record.setdefault("id", str(uuid.uuid4()))
        self.conn.execute(
            """
            INSERT OR REPLACE INTO reconciliation_runs (
              id, organization_id, provider, run_started_at, run_finished_at, run_status,
              matched_count, mismatched_count, missing_internal_count, missing_provider_count,
              result_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["organization_id"],
                record["provider"],
                record["run_started_at"],
                record["run_finished_at"],
                record["run_status"],
                record["matched_count"],
                record["mismatched_count"],
                record["missing_internal_count"],
                record["missing_provider_count"],
                self._json(record["result_payload"]),
            ),
        )
        self.conn.commit()
        return record

    def get_reconciliation_run(self, run_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM reconciliation_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        return self._row_to_dict(row)

    def list_reconciliation_runs_by_org(self, *, organization_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM reconciliation_runs
            WHERE organization_id = ?
            ORDER BY run_started_at DESC
            LIMIT ?
            """,
            (organization_id, max(1, int(limit))),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def insert_outbox_event(self, event: dict) -> dict:
        record = dict(event)
        record.setdefault("event_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self.conn.execute(
            """
            INSERT INTO stage3_event_outbox (
              event_id, organization_id, event_type, event_version, aggregate_type,
              aggregate_id, idempotency_key, trace_id, payload, occurred_at,
              produced_by, publish_state, publish_attempts, published_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["event_id"],
                record["organization_id"],
                record["event_type"],
                record["event_version"],
                record["aggregate_type"],
                record["aggregate_id"],
                record["idempotency_key"],
                record["trace_id"],
                self._json(record["payload"]),
                record["occurred_at"],
                record["produced_by"],
                record.get("publish_state", "pending"),
                int(record.get("publish_attempts", 0)),
                record.get("published_at"),
                record["created_at"],
            ),
        )
        self.conn.commit()
        return record

    def list_outbox_events(self, *, publish_state: str | None = "pending", limit: int = 100) -> list[dict]:
        if publish_state is None:
            rows = self.conn.execute(
                """
                SELECT * FROM stage3_event_outbox
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM stage3_event_outbox
                WHERE publish_state = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (publish_state, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def mark_outbox_event_published(self, event_id: str) -> dict:
        published_at = self._now_iso()
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE stage3_event_outbox
                SET publish_state = 'published', published_at = ?, publish_attempts = publish_attempts + 1
                WHERE event_id = ?
                """,
                (published_at, event_id),
            )
            if cur.rowcount == 0:
                raise KeyError("event not found")
        row = self.conn.execute(
            "SELECT * FROM stage3_event_outbox WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        out = self._row_to_dict(row)
        if not out:
            raise KeyError("event not found")
        return out
