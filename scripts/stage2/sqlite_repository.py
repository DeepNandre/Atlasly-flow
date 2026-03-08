from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid


class Stage2SQLiteRepository:
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
            CREATE TABLE IF NOT EXISTS intake_sessions (
              session_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              permit_type TEXT NOT NULL,
              ahj_id TEXT NOT NULL,
              current_step TEXT NOT NULL,
              status TEXT NOT NULL,
              answers_json TEXT NOT NULL,
              version INTEGER NOT NULL,
              completed_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              UNIQUE (organization_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS permit_applications (
              application_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              intake_session_id TEXT NOT NULL,
              permit_type TEXT NOT NULL,
              ahj_id TEXT NOT NULL,
              form_template_id TEXT NOT NULL,
              mapping_version INTEGER NOT NULL,
              application_payload TEXT NOT NULL,
              validation_summary TEXT NOT NULL,
              generated_at TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              UNIQUE (organization_id, idempotency_key),
              FOREIGN KEY (intake_session_id) REFERENCES intake_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS portal_sync_runs (
              run_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              connector TEXT NOT NULL,
              ahj_id TEXT NOT NULL,
              status TEXT NOT NULL,
              run_started_at TEXT NOT NULL,
              run_finished_at TEXT,
              dry_run INTEGER NOT NULL DEFAULT 0,
              force_run INTEGER NOT NULL DEFAULT 0,
              idempotency_key TEXT NOT NULL,
              UNIQUE (organization_id, connector, ahj_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS connector_credentials (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              connector TEXT NOT NULL,
              ahj_id TEXT,
              credential_ref TEXT NOT NULL,
              auth_scheme TEXT NOT NULL DEFAULT 'bearer',
              scopes_json TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'active',
              last_validated_at TEXT,
              expires_at TEXT,
              rotation_due_at TEXT,
              created_by TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS external_permit_bindings (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              connector TEXT NOT NULL,
              ahj_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              external_permit_id TEXT NOT NULL,
              external_record_ref TEXT,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_by TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE (organization_id, connector, ahj_id, permit_id),
              UNIQUE (organization_id, connector, ahj_id, external_permit_id)
            );

            CREATE TABLE IF NOT EXISTS permit_status_events (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              raw_status TEXT NOT NULL,
              normalized_status TEXT,
              source TEXT NOT NULL,
              confidence REAL NOT NULL,
              observed_at TEXT NOT NULL,
              parser_version TEXT,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE (organization_id, event_hash)
            );

            CREATE TABLE IF NOT EXISTS status_source_provenance (
              id TEXT PRIMARY KEY,
              status_event_id TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_ref TEXT NOT NULL,
              source_payload_hash TEXT NOT NULL,
              parser_version TEXT,
              ingested_at TEXT NOT NULL,
              FOREIGN KEY (status_event_id) REFERENCES permit_status_events(id)
            );

            CREATE TABLE IF NOT EXISTS status_transition_reviews (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              status_event_id TEXT NOT NULL,
              from_status TEXT NOT NULL,
              to_status TEXT NOT NULL,
              rejection_reason TEXT NOT NULL,
              resolution_state TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE (status_event_id),
              FOREIGN KEY (status_event_id) REFERENCES permit_status_events(id)
            );

            CREATE TABLE IF NOT EXISTS permit_status_projections (
              permit_id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              current_status TEXT NOT NULL,
              source_event_id TEXT,
              confidence REAL NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS status_reconciliation_runs (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              connector TEXT,
              ahj_id TEXT,
              run_started_at TEXT NOT NULL,
              run_finished_at TEXT NOT NULL,
              status TEXT NOT NULL,
              totals_json TEXT NOT NULL,
              mismatch_summary_json TEXT NOT NULL,
              ruleset_version TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS status_drift_alerts (
              id TEXT PRIMARY KEY,
              organization_id TEXT NOT NULL,
              permit_id TEXT,
              connector TEXT,
              ahj_id TEXT,
              drift_type TEXT NOT NULL,
              severity TEXT NOT NULL,
              status TEXT NOT NULL,
              details_json TEXT NOT NULL,
              detected_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stage2_event_outbox (
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
              created_at TEXT NOT NULL,
              UNIQUE (organization_id, idempotency_key, event_type)
            );

            CREATE INDEX IF NOT EXISTS idx_connector_credentials_org_connector
              ON connector_credentials (organization_id, connector, updated_at DESC);

            CREATE UNIQUE INDEX IF NOT EXISTS uq_connector_credentials_org_connector_ahj
              ON connector_credentials (organization_id, connector, IFNULL(ahj_id, '__global__'));

            CREATE INDEX IF NOT EXISTS idx_external_permit_bindings_org_connector
              ON external_permit_bindings (organization_id, connector, ahj_id, updated_at DESC);
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
        for key in (
            "answers_json",
            "application_payload",
            "validation_summary",
            "totals_json",
            "mismatch_summary_json",
            "details_json",
            "payload",
            "scopes_json",
            "metadata_json",
        ):
            if key in out and isinstance(out[key], str):
                out[key] = json.loads(out[key])
        return out

    def upsert_external_permit_binding(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str,
        permit_id: str,
        external_permit_id: str,
        external_record_ref: str | None,
        metadata_json: dict | None,
        created_by: str | None,
    ) -> dict:
        now = self._now_iso()
        existing = self.conn.execute(
            """
            SELECT * FROM external_permit_bindings
            WHERE organization_id = ? AND connector = ? AND ahj_id = ? AND permit_id = ?
            """,
            (organization_id, connector, ahj_id, permit_id),
        ).fetchone()
        record = {
            "id": str(uuid.uuid4()) if existing is None else str(existing["id"]),
            "organization_id": organization_id,
            "connector": connector,
            "ahj_id": ahj_id,
            "permit_id": permit_id,
            "external_permit_id": external_permit_id,
            "external_record_ref": external_record_ref,
            "metadata_json": metadata_json or {},
            "created_by": created_by,
            "created_at": now if existing is None else str(existing["created_at"]),
            "updated_at": now,
        }
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO external_permit_bindings (
                  id, organization_id, connector, ahj_id, permit_id, external_permit_id,
                  external_record_ref, metadata_json, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization_id, connector, ahj_id, permit_id) DO UPDATE SET
                  external_permit_id = excluded.external_permit_id,
                  external_record_ref = excluded.external_record_ref,
                  metadata_json = excluded.metadata_json,
                  created_by = excluded.created_by,
                  updated_at = excluded.updated_at
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record["connector"],
                    record["ahj_id"],
                    record["permit_id"],
                    record["external_permit_id"],
                    record["external_record_ref"],
                    self._json(record["metadata_json"]),
                    record["created_by"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        return record

    def list_external_permit_bindings(
        self,
        *,
        organization_id: str,
        connector: str | None = None,
        ahj_id: str | None = None,
        permit_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        clauses = ["organization_id = ?"]
        params: list[object] = [organization_id]
        if connector:
            clauses.append("connector = ?")
            params.append(connector)
        if ahj_id:
            clauses.append("ahj_id = ?")
            params.append(ahj_id)
        if permit_id:
            clauses.append("permit_id = ?")
            params.append(permit_id)
        params.append(max(1, int(limit)))
        rows = self.conn.execute(
            f"""
            SELECT * FROM external_permit_bindings
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_external_permit_binding_by_external_id(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str,
        external_permit_id: str,
    ) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM external_permit_bindings
            WHERE organization_id = ? AND connector = ? AND ahj_id = ? AND external_permit_id = ?
            """,
            (organization_id, connector, ahj_id, external_permit_id),
        ).fetchone()
        return self._row_to_dict(row)

    def count_rows(self, table_name: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) AS c FROM {table_name}").fetchone()
        return int(row["c"])

    def create_or_get_intake_session(self, *, organization_id: str, idempotency_key: str, session: dict) -> tuple[bool, dict]:
        row = self.conn.execute(
            "SELECT * FROM intake_sessions WHERE organization_id = ? AND idempotency_key = ?",
            (organization_id, idempotency_key),
        ).fetchone()
        if row:
            record = self._row_to_dict(row)
            record["session_id"] = record.pop("session_id")
            record["answers"] = record.pop("answers_json")
            return False, record

        record = dict(session)
        record.setdefault("session_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        record.setdefault("updated_at", record["created_at"])
        record.setdefault("version", 1)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO intake_sessions (
                  session_id, organization_id, project_id, permit_type, ahj_id,
                  current_step, status, answers_json, version, completed_at,
                  created_at, updated_at, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["session_id"],
                    record["organization_id"],
                    record["project_id"],
                    record["permit_type"],
                    record["ahj_id"],
                    record["current_step"],
                    record["status"],
                    self._json(record["answers"]),
                    record["version"],
                    record.get("completed_at"),
                    record["created_at"],
                    record["updated_at"],
                    idempotency_key,
                ),
            )
        return True, record

    def get_intake_session(self, session_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM intake_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None
        record = self._row_to_dict(row)
        record["session_id"] = record.pop("session_id")
        record["answers"] = record.pop("answers_json")
        return record

    def save_intake_session(self, session: dict) -> dict:
        record = dict(session)
        with self.conn:
            self.conn.execute(
                """
                UPDATE intake_sessions
                SET current_step = ?, status = ?, answers_json = ?, version = ?,
                    completed_at = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    record["current_step"],
                    record["status"],
                    self._json(record["answers"]),
                    record["version"],
                    record.get("completed_at"),
                    record["updated_at"],
                    record["session_id"],
                ),
            )
        return record

    def create_or_get_permit_application(
        self, *, organization_id: str, idempotency_key: str, application: dict
    ) -> tuple[bool, dict]:
        row = self.conn.execute(
            "SELECT * FROM permit_applications WHERE organization_id = ? AND idempotency_key = ?",
            (organization_id, idempotency_key),
        ).fetchone()
        if row:
            record = self._row_to_dict(row)
            record["application_id"] = record.pop("application_id")
            return False, record

        record = dict(application)
        record.setdefault("application_id", str(uuid.uuid4()))
        record.setdefault("generated_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO permit_applications (
                  application_id, organization_id, project_id, permit_id, intake_session_id,
                  permit_type, ahj_id, form_template_id, mapping_version,
                  application_payload, validation_summary, generated_at, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["application_id"],
                    record["organization_id"],
                    record["project_id"],
                    record["permit_id"],
                    record["intake_session_id"],
                    record["permit_type"],
                    record["ahj_id"],
                    record["form_template_id"],
                    record["mapping_version"],
                    self._json(record["application_payload"]),
                    self._json(record["validation_summary"]),
                    record["generated_at"],
                    idempotency_key,
                ),
            )
        return True, record

    def create_or_get_poll_run(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str,
        idempotency_key: str,
        run: dict,
    ) -> tuple[bool, dict]:
        row = self.conn.execute(
            """
            SELECT * FROM portal_sync_runs
            WHERE organization_id = ? AND connector = ? AND ahj_id = ? AND idempotency_key = ?
            """,
            (organization_id, connector, ahj_id, idempotency_key),
        ).fetchone()
        if row:
            record = self._row_to_dict(row)
            record["run_id"] = record.pop("run_id")
            record["dry_run"] = bool(record["dry_run"])
            record["force"] = bool(record.pop("force_run"))
            return False, record

        record = dict(run)
        record.setdefault("run_id", str(uuid.uuid4()))
        record.setdefault("run_started_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO portal_sync_runs (
                  run_id, organization_id, connector, ahj_id, status, run_started_at,
                  run_finished_at, dry_run, force_run, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["run_id"],
                    record["organization_id"],
                    record["connector"],
                    record["ahj_id"],
                    record["status"],
                    record["run_started_at"],
                    record.get("run_finished_at"),
                    1 if record.get("dry_run", False) else 0,
                    1 if record.get("force", False) else 0,
                    idempotency_key,
                ),
            )
        return True, record

    def save_poll_run(self, run: dict) -> dict:
        record = dict(run)
        with self.conn:
            self.conn.execute(
                """
                UPDATE portal_sync_runs
                SET status = ?, run_finished_at = ?
                WHERE run_id = ?
                """,
                (
                    record["status"],
                    record.get("run_finished_at"),
                    record["run_id"],
                ),
            )
        return record

    def get_poll_run(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM portal_sync_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        record = self._row_to_dict(row)
        record["run_id"] = record.pop("run_id")
        record["dry_run"] = bool(record["dry_run"])
        record["force"] = bool(record.pop("force_run"))
        return record

    def list_recent_poll_runs(self, *, organization_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM portal_sync_runs
            WHERE organization_id = ?
            ORDER BY run_started_at DESC
            LIMIT ?
            """,
            (organization_id, max(1, int(limit))),
        ).fetchall()
        out: list[dict] = []
        for row in rows:
            record = self._row_to_dict(row)
            record["run_id"] = record.pop("run_id")
            record["dry_run"] = bool(record["dry_run"])
            record["force"] = bool(record.pop("force_run"))
            out.append(record)
        return out

    def upsert_connector_credential(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
        credential: dict,
    ) -> dict:
        now = self._now_iso()
        existing = self.conn.execute(
            """
            SELECT * FROM connector_credentials
            WHERE organization_id = ? AND connector = ? AND IFNULL(ahj_id, '__global__') = IFNULL(?, '__global__')
            """,
            (organization_id, connector, ahj_id),
        ).fetchone()
        if existing:
            row = self._row_to_dict(existing) or {}
            updated = dict(row)
            updated.update(dict(credential))
            updated["id"] = row["id"]
            updated["organization_id"] = organization_id
            updated["connector"] = connector
            updated["ahj_id"] = ahj_id
            updated["updated_at"] = now
            updated.setdefault("created_at", row.get("created_at", now))
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE connector_credentials
                    SET credential_ref = ?, auth_scheme = ?, scopes_json = ?, status = ?, last_validated_at = ?,
                        expires_at = ?, rotation_due_at = ?, created_by = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        updated["credential_ref"],
                        updated.get("auth_scheme", "bearer"),
                        self._json(updated.get("scopes_json", [])),
                        updated.get("status", "active"),
                        updated.get("last_validated_at"),
                        updated.get("expires_at"),
                        updated.get("rotation_due_at"),
                        updated.get("created_by"),
                        updated["updated_at"],
                        updated["id"],
                    ),
                )
            updated["scopes"] = updated.pop("scopes_json", [])
            return updated

        record = dict(credential)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("organization_id", organization_id)
        record.setdefault("connector", connector)
        record.setdefault("ahj_id", ahj_id)
        record.setdefault("auth_scheme", "bearer")
        record.setdefault("status", "active")
        record.setdefault("scopes_json", [])
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO connector_credentials (
                  id, organization_id, connector, ahj_id, credential_ref, auth_scheme, scopes_json, status,
                  last_validated_at, expires_at, rotation_due_at, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record["connector"],
                    record["ahj_id"],
                    record["credential_ref"],
                    record["auth_scheme"],
                    self._json(record.get("scopes_json", [])),
                    record["status"],
                    record.get("last_validated_at"),
                    record.get("expires_at"),
                    record.get("rotation_due_at"),
                    record.get("created_by"),
                    record["created_at"],
                    record["updated_at"],
                ),
            )
        record["scopes"] = record.pop("scopes_json", [])
        return record

    def get_connector_credential(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
    ) -> dict | None:
        row = self.conn.execute(
            """
            SELECT * FROM connector_credentials
            WHERE organization_id = ? AND connector = ? AND IFNULL(ahj_id, '__global__') = IFNULL(?, '__global__')
            """,
            (organization_id, connector, ahj_id),
        ).fetchone()
        if row is None and ahj_id is not None:
            row = self.conn.execute(
                """
                SELECT * FROM connector_credentials
                WHERE organization_id = ? AND connector = ? AND ahj_id IS NULL
                """,
                (organization_id, connector),
            ).fetchone()
        record = self._row_to_dict(row)
        if not record:
            return None
        record["scopes"] = record.pop("scopes_json", [])
        return record

    def list_connector_credentials(
        self,
        *,
        organization_id: str,
        connector: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        if connector is None:
            rows = self.conn.execute(
                """
                SELECT * FROM connector_credentials
                WHERE organization_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (organization_id, max(1, int(limit))),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM connector_credentials
                WHERE organization_id = ? AND connector = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (organization_id, connector, max(1, int(limit))),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            record = self._row_to_dict(row)
            if not record:
                continue
            record["scopes"] = record.pop("scopes_json", [])
            out.append(record)
        return out

    def insert_status_event_with_provenance(self, *, event: dict, provenance: dict) -> tuple[bool, dict]:
        row = self.conn.execute(
            "SELECT * FROM permit_status_events WHERE organization_id = ? AND event_hash = ?",
            (event["organization_id"], event["event_hash"]),
        ).fetchone()
        if row:
            record = self._row_to_dict(row)
            return False, record

        record = dict(event)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO permit_status_events (
                  id, organization_id, permit_id, raw_status, normalized_status,
                  source, confidence, observed_at, parser_version, event_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record["permit_id"],
                    record["raw_status"],
                    record["normalized_status"],
                    record["source"],
                    record["confidence"],
                    record["observed_at"],
                    record.get("parser_version"),
                    record["event_hash"],
                    record["created_at"],
                ),
            )
            prov = dict(provenance)
            prov.setdefault("id", str(uuid.uuid4()))
            prov.setdefault("ingested_at", self._now_iso())
            self.conn.execute(
                """
                INSERT INTO status_source_provenance (
                  id, status_event_id, source_type, source_ref, source_payload_hash,
                  parser_version, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prov["id"],
                    record["id"],
                    prov["source_type"],
                    prov["source_ref"],
                    prov["source_payload_hash"],
                    prov.get("parser_version"),
                    prov["ingested_at"],
                ),
            )
        return True, record

    def list_status_events_by_permit(self, *, organization_id: str, permit_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM permit_status_events
            WHERE organization_id = ? AND permit_id = ?
            ORDER BY observed_at DESC
            """,
            (organization_id, permit_id),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_status_provenance(self, status_event_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM status_source_provenance WHERE status_event_id = ?",
            (status_event_id,),
        ).fetchone()
        return self._row_to_dict(row)

    def insert_transition_review(self, review: dict) -> dict:
        record = dict(review)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO status_transition_reviews (
                  id, organization_id, permit_id, status_event_id,
                  from_status, to_status, rejection_reason, resolution_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record["permit_id"],
                    record["status_event_id"],
                    record["from_status"],
                    record["to_status"],
                    record["rejection_reason"],
                    record["resolution_state"],
                    record["created_at"],
                ),
            )
        return record

    def list_transition_reviews_by_org(
        self,
        *,
        organization_id: str,
        limit: int = 50,
        resolution_state: str | None = None,
    ) -> list[dict]:
        if resolution_state is None:
            rows = self.conn.execute(
                """
                SELECT r.*, e.raw_status, e.confidence, e.observed_at
                FROM status_transition_reviews AS r
                LEFT JOIN permit_status_events AS e ON e.id = r.status_event_id
                WHERE r.organization_id = ?
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (organization_id, max(1, int(limit))),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT r.*, e.raw_status, e.confidence, e.observed_at
                FROM status_transition_reviews AS r
                LEFT JOIN permit_status_events AS e ON e.id = r.status_event_id
                WHERE r.organization_id = ? AND r.resolution_state = ?
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                (organization_id, resolution_state, max(1, int(limit))),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_transition_review_resolution(
        self,
        *,
        organization_id: str,
        review_id: str,
        resolution_state: str,
    ) -> dict:
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE status_transition_reviews
                SET resolution_state = ?
                WHERE organization_id = ? AND id = ?
                """,
                (resolution_state, organization_id, review_id),
            )
            if cur.rowcount == 0:
                raise KeyError("review not found")
        row = self.conn.execute(
            """
            SELECT r.*, e.raw_status, e.confidence, e.observed_at
            FROM status_transition_reviews AS r
            LEFT JOIN permit_status_events AS e ON e.id = r.status_event_id
            WHERE r.organization_id = ? AND r.id = ?
            """,
            (organization_id, review_id),
        ).fetchone()
        record = self._row_to_dict(row)
        if not record:
            raise KeyError("review not found")
        return record

    def upsert_status_projection(self, projection: dict) -> dict:
        record = dict(projection)
        record.setdefault("updated_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO permit_status_projections (
                  permit_id, organization_id, current_status, source_event_id, confidence, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(permit_id) DO UPDATE SET
                  organization_id = excluded.organization_id,
                  current_status = excluded.current_status,
                  source_event_id = excluded.source_event_id,
                  confidence = excluded.confidence,
                  updated_at = excluded.updated_at
                """,
                (
                    record["permit_id"],
                    record["organization_id"],
                    record["current_status"],
                    record.get("source_event_id"),
                    record["confidence"],
                    record["updated_at"],
                ),
            )
        return record

    def get_status_projection(self, permit_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM permit_status_projections WHERE permit_id = ?",
            (permit_id,),
        ).fetchone()
        return self._row_to_dict(row)

    def save_reconciliation_run(self, run: dict) -> dict:
        record = dict(run)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO status_reconciliation_runs (
                  id, organization_id, connector, ahj_id, run_started_at, run_finished_at,
                  status, totals_json, mismatch_summary_json, ruleset_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record.get("connector"),
                    record.get("ahj_id"),
                    record["run_started_at"],
                    record["run_finished_at"],
                    record["status"],
                    self._json(record["totals_json"]),
                    self._json(record["mismatch_summary_json"]),
                    record["ruleset_version"],
                    record["created_at"],
                ),
            )
        return record

    def list_recent_reconciliation_runs_by_org(self, *, organization_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM status_reconciliation_runs
            WHERE organization_id = ?
            ORDER BY run_started_at DESC
            LIMIT ?
            """,
            (organization_id, max(1, int(limit))),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def insert_drift_alert(self, alert: dict) -> dict:
        record = dict(alert)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO status_drift_alerts (
                  id, organization_id, permit_id, connector, ahj_id, drift_type, severity,
                  status, details_json, detected_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["organization_id"],
                    record.get("permit_id"),
                    record.get("connector"),
                    record.get("ahj_id"),
                    record["drift_type"],
                    record["severity"],
                    record["status"],
                    self._json(record.get("details_json", {})),
                    record["detected_at"],
                    record["created_at"],
                ),
            )
        return record

    def list_drift_alerts_by_org(self, organization_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM status_drift_alerts WHERE organization_id = ? ORDER BY detected_at DESC",
            (organization_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_drift_alert_status(self, *, organization_id: str, alert_id: str, status: str) -> dict:
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE status_drift_alerts
                SET status = ?
                WHERE organization_id = ? AND id = ?
                """,
                (status, organization_id, alert_id),
            )
            if cur.rowcount == 0:
                raise KeyError("alert not found")
        row = self.conn.execute(
            "SELECT * FROM status_drift_alerts WHERE organization_id = ? AND id = ?",
            (organization_id, alert_id),
        ).fetchone()
        record = self._row_to_dict(row)
        if not record:
            raise KeyError("alert not found")
        return record

    def insert_outbox_event(self, event: dict) -> dict:
        record = dict(event)
        record.setdefault("event_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO stage2_event_outbox (
                  event_id, organization_id, event_type, event_version, aggregate_type, aggregate_id,
                  idempotency_key, trace_id, payload, occurred_at, produced_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    record["created_at"],
                ),
            )
            row = self.conn.execute(
                """
                SELECT * FROM stage2_event_outbox
                WHERE organization_id = ? AND idempotency_key = ? AND event_type = ?
                """,
                (
                    record["organization_id"],
                    record["idempotency_key"],
                    record["event_type"],
                ),
            ).fetchone()
        return self._row_to_dict(row) or record
