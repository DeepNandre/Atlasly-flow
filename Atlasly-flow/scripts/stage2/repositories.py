from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass
class Stage2PersistenceStore:
    intake_sessions: dict[str, dict]
    intake_session_by_idempotency: dict[tuple[str, str], str]
    permit_applications: dict[str, dict]
    application_by_idempotency: dict[tuple[str, str], str]
    portal_sync_runs: dict[str, dict]
    poll_run_by_idempotency: dict[tuple[str, str, str, str], str]
    permit_status_events: dict[str, dict]
    status_event_by_org_hash: dict[tuple[str, str], str]
    status_provenance_by_event_id: dict[str, dict]
    status_transition_reviews: dict[str, dict]
    permit_status_projections: dict[str, dict]
    status_reconciliation_runs: dict[str, dict]
    status_drift_alerts: dict[str, dict]
    connector_credentials: dict[str, dict]
    connector_credential_by_scope: dict[tuple[str, str, str | None], str]
    outbox_events: dict[str, dict]
    outbox_by_idem_event: dict[tuple[str, str, str], str]

    @classmethod
    def empty(cls) -> "Stage2PersistenceStore":
        return cls({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})


class Stage2Repository:
    def __init__(self, store: Stage2PersistenceStore):
        self._store = store

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_or_get_intake_session(
        self, *, organization_id: str, idempotency_key: str, session: dict
    ) -> tuple[bool, dict]:
        key = (organization_id, idempotency_key)
        existing_id = self._store.intake_session_by_idempotency.get(key)
        if existing_id:
            return False, self._store.intake_sessions[existing_id]

        record = dict(session)
        record.setdefault("session_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        record.setdefault("updated_at", record["created_at"])
        record.setdefault("version", 1)
        self._store.intake_sessions[record["session_id"]] = record
        self._store.intake_session_by_idempotency[key] = record["session_id"]
        return True, record

    def get_intake_session(self, session_id: str) -> dict | None:
        return self._store.intake_sessions.get(session_id)

    def save_intake_session(self, session: dict) -> dict:
        record = dict(session)
        self._store.intake_sessions[record["session_id"]] = record
        return record

    def create_or_get_permit_application(
        self, *, organization_id: str, idempotency_key: str, application: dict
    ) -> tuple[bool, dict]:
        key = (organization_id, idempotency_key)
        existing_id = self._store.application_by_idempotency.get(key)
        if existing_id:
            return False, self._store.permit_applications[existing_id]

        record = dict(application)
        record.setdefault("application_id", str(uuid.uuid4()))
        record.setdefault("generated_at", self._now_iso())
        self._store.permit_applications[record["application_id"]] = record
        self._store.application_by_idempotency[key] = record["application_id"]
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
        key = (organization_id, connector, ahj_id, idempotency_key)
        existing_id = self._store.poll_run_by_idempotency.get(key)
        if existing_id:
            return False, self._store.portal_sync_runs[existing_id]

        record = dict(run)
        record.setdefault("run_id", str(uuid.uuid4()))
        record.setdefault("run_started_at", self._now_iso())
        self._store.portal_sync_runs[record["run_id"]] = record
        self._store.poll_run_by_idempotency[key] = record["run_id"]
        return True, record

    def save_poll_run(self, run: dict) -> dict:
        record = dict(run)
        self._store.portal_sync_runs[record["run_id"]] = record
        return record

    def get_poll_run(self, run_id: str) -> dict | None:
        return self._store.portal_sync_runs.get(run_id)

    def insert_status_event_with_provenance(
        self, *, event: dict, provenance: dict
    ) -> tuple[bool, dict]:
        dedupe_key = (event["organization_id"], event["event_hash"])
        existing_id = self._store.status_event_by_org_hash.get(dedupe_key)
        if existing_id:
            return False, self._store.permit_status_events[existing_id]

        record = dict(event)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self._store.permit_status_events[record["id"]] = record
        self._store.status_event_by_org_hash[dedupe_key] = record["id"]

        prov = dict(provenance)
        prov.setdefault("id", str(uuid.uuid4()))
        prov.setdefault("status_event_id", record["id"])
        prov.setdefault("ingested_at", self._now_iso())
        self._store.status_provenance_by_event_id[record["id"]] = prov
        return True, record

    def list_status_events_by_permit(self, *, organization_id: str, permit_id: str) -> list[dict]:
        rows = [
            event
            for event in self._store.permit_status_events.values()
            if event["organization_id"] == organization_id and event["permit_id"] == permit_id
        ]
        return sorted(rows, key=lambda r: r["observed_at"], reverse=True)

    def get_status_provenance(self, status_event_id: str) -> dict | None:
        return self._store.status_provenance_by_event_id.get(status_event_id)

    def insert_transition_review(self, review: dict) -> dict:
        record = dict(review)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self._store.status_transition_reviews[record["id"]] = record
        return record

    def list_transition_reviews_by_org(
        self,
        *,
        organization_id: str,
        limit: int = 50,
        resolution_state: str | None = None,
    ) -> list[dict]:
        rows = [row for row in self._store.status_transition_reviews.values() if row["organization_id"] == organization_id]
        if resolution_state is not None:
            rows = [row for row in rows if row.get("resolution_state") == resolution_state]
        rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[: max(1, int(limit))]

    def update_transition_review_resolution(
        self,
        *,
        organization_id: str,
        review_id: str,
        resolution_state: str,
    ) -> dict:
        row = self._store.status_transition_reviews.get(review_id)
        if not row or row.get("organization_id") != organization_id:
            raise KeyError("review not found")
        updated = dict(row)
        updated["resolution_state"] = resolution_state
        self._store.status_transition_reviews[review_id] = updated
        return updated

    def upsert_status_projection(self, projection: dict) -> dict:
        record = dict(projection)
        record.setdefault("updated_at", self._now_iso())
        self._store.permit_status_projections[record["permit_id"]] = record
        return record

    def get_status_projection(self, permit_id: str) -> dict | None:
        return self._store.permit_status_projections.get(permit_id)

    def save_reconciliation_run(self, run: dict) -> dict:
        record = dict(run)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self._store.status_reconciliation_runs[record["id"]] = record
        return record

    def insert_drift_alert(self, alert: dict) -> dict:
        record = dict(alert)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self._store.status_drift_alerts[record["id"]] = record
        return record

    def list_drift_alerts_by_org(self, organization_id: str) -> list[dict]:
        rows = [a for a in self._store.status_drift_alerts.values() if a["organization_id"] == organization_id]
        return sorted(rows, key=lambda r: r.get("detected_at", r.get("created_at", "")), reverse=True)

    def update_drift_alert_status(self, *, organization_id: str, alert_id: str, status: str) -> dict:
        row = self._store.status_drift_alerts.get(alert_id)
        if not row or row.get("organization_id") != organization_id:
            raise KeyError("alert not found")
        updated = dict(row)
        updated["status"] = status
        self._store.status_drift_alerts[alert_id] = updated
        return updated

    def upsert_connector_credential(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
        credential: dict,
    ) -> dict:
        key = (organization_id, connector, ahj_id)
        existing_id = self._store.connector_credential_by_scope.get(key)
        record = dict(credential)
        if existing_id:
            persisted = dict(self._store.connector_credentials[existing_id])
            persisted.update(record)
            persisted["id"] = existing_id
            persisted.setdefault("updated_at", self._now_iso())
            self._store.connector_credentials[existing_id] = persisted
            return persisted

        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("organization_id", organization_id)
        record.setdefault("connector", connector)
        record.setdefault("ahj_id", ahj_id)
        record.setdefault("created_at", self._now_iso())
        record.setdefault("updated_at", record["created_at"])
        self._store.connector_credentials[record["id"]] = record
        self._store.connector_credential_by_scope[key] = record["id"]
        return record

    def get_connector_credential(
        self,
        *,
        organization_id: str,
        connector: str,
        ahj_id: str | None,
    ) -> dict | None:
        direct_id = self._store.connector_credential_by_scope.get((organization_id, connector, ahj_id))
        if direct_id:
            return self._store.connector_credentials.get(direct_id)
        if ahj_id is not None:
            fallback_id = self._store.connector_credential_by_scope.get((organization_id, connector, None))
            if fallback_id:
                return self._store.connector_credentials.get(fallback_id)
        return None

    def list_connector_credentials(
        self,
        *,
        organization_id: str,
        connector: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        rows = [row for row in self._store.connector_credentials.values() if row["organization_id"] == organization_id]
        if connector is not None:
            rows = [row for row in rows if row["connector"] == connector]
        rows = sorted(rows, key=lambda r: r.get("updated_at", r.get("created_at", "")), reverse=True)
        return rows[: max(1, int(limit))]

    def insert_outbox_event(self, event: dict) -> dict:
        idem = (event["organization_id"], event["idempotency_key"], event["event_type"])
        existing_id = self._store.outbox_by_idem_event.get(idem)
        if existing_id:
            return self._store.outbox_events[existing_id]

        record = dict(event)
        record.setdefault("event_id", str(uuid.uuid4()))
        record.setdefault("created_at", self._now_iso())
        self._store.outbox_events[record["event_id"]] = record
        self._store.outbox_by_idem_event[idem] = record["event_id"]
        return record
