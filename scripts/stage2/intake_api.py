from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from scripts.stage2.repositories import Stage2Repository

PERMIT_TYPES = {"commercial_ti", "rooftop_solar", "electrical_service_upgrade"}
INTAKE_WRITE_ROLES = {"owner", "admin", "pm"}

BASE_REQUIRED_FIELDS = {
    "project_name",
    "project_address_line1",
    "city",
    "state",
    "postal_code",
    "scope_summary",
    "valuation_usd",
    "owner_legal_name",
    "applicant_email",
    "contractor_company_name",
}

PERMIT_SPECIFIC_REQUIRED_FIELDS = {
    "commercial_ti": {"building_area_sqft", "sprinklered_flag"},
    "rooftop_solar": {"solar_kw_dc", "solar_inverter_count", "contractor_license_number"},
    "electrical_service_upgrade": {
        "electrical_panel_amps_existing",
        "electrical_panel_amps_proposed",
        "contractor_license_number",
    },
}


class IntakeRequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    requester_role: str
    user_id: str | None = None


@dataclass
class IntakeStore:
    sessions_by_id: dict[str, dict]
    applications_by_id: dict[str, dict]
    intake_session_by_org_idempotency: dict[tuple[str, str], str]
    app_generation_by_org_idempotency: dict[tuple[str, str], str]
    outbox_events: list[dict]

    @classmethod
    def empty(cls) -> "IntakeStore":
        return cls({}, {}, {}, {}, [])


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _event_envelope(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    organization_id: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    produced_by: str,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": _iso(occurred_at),
        "produced_by": produced_by,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def _require_write_role(auth_context: AuthContext) -> None:
    if auth_context.requester_role not in INTAKE_WRITE_ROLES:
        raise IntakeRequestError(403, "forbidden", "role cannot modify intake/application")


def _validate_completed_answers(*, permit_type: str, answers: dict[str, object]) -> None:
    required = set(BASE_REQUIRED_FIELDS) | set(PERMIT_SPECIFIC_REQUIRED_FIELDS[permit_type])
    missing = sorted([field for field in required if field not in answers or answers[field] in ("", None)])
    if missing:
        raise IntakeRequestError(
            422,
            "validation_error",
            f"missing required intake fields for completion: {', '.join(missing)}",
        )

    if permit_type == "electrical_service_upgrade":
        existing = Decimal(str(answers["electrical_panel_amps_existing"]))
        proposed = Decimal(str(answers["electrical_panel_amps_proposed"]))
        if proposed < existing:
            raise IntakeRequestError(
                422,
                "validation_error",
                "electrical_panel_amps_proposed must be >= electrical_panel_amps_existing",
            )


def create_intake_session(
    *,
    project_id: str,
    permit_type: str,
    ahj_id: str | None,
    seed_answers: dict[str, object] | None,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: IntakeStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    if not idempotency_key.strip():
        raise IntakeRequestError(400, "invalid_request", "Idempotency-Key is required")
    if permit_type not in PERMIT_TYPES:
        raise IntakeRequestError(422, "validation_error", "unsupported permit_type")
    if not ahj_id or not ahj_id.strip():
        raise IntakeRequestError(422, "validation_error", "ahj_id is required")

    key = (auth_context.organization_id, idempotency_key)
    existing_id = store.intake_session_by_org_idempotency.get(key)
    if existing_id:
        return 200, store.sessions_by_id[existing_id]

    ts = now or datetime.now(timezone.utc)
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "organization_id": auth_context.organization_id,
        "project_id": project_id,
        "permit_type": permit_type,
        "ahj_id": ahj_id,
        "current_step": "project",
        "status": "in_progress",
        "answers": dict(seed_answers or {}),
        "version": 1,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.sessions_by_id[session_id] = session
    store.intake_session_by_org_idempotency[key] = session_id
    return 201, session


def create_intake_session_persisted(
    *,
    project_id: str,
    permit_type: str,
    ahj_id: str | None,
    seed_answers: dict[str, object] | None,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    repository: Stage2Repository,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    if not idempotency_key.strip():
        raise IntakeRequestError(400, "invalid_request", "Idempotency-Key is required")
    if permit_type not in PERMIT_TYPES:
        raise IntakeRequestError(422, "validation_error", "unsupported permit_type")
    if not ahj_id or not ahj_id.strip():
        raise IntakeRequestError(422, "validation_error", "ahj_id is required")

    ts = now or datetime.now(timezone.utc)
    created, session = repository.create_or_get_intake_session(
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        session={
            "organization_id": auth_context.organization_id,
            "project_id": project_id,
            "permit_type": permit_type,
            "ahj_id": ahj_id,
            "current_step": "project",
            "status": "in_progress",
            "answers": dict(seed_answers or {}),
            "version": 1,
            "created_at": _iso(ts),
            "updated_at": _iso(ts),
        },
    )
    return (201 if created else 200), session


def update_intake_session(
    *,
    session_id: str,
    if_match_version: int,
    payload: dict[str, object],
    trace_id: str,
    auth_context: AuthContext,
    store: IntakeStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    session = store.sessions_by_id.get(session_id)
    if not session:
        raise IntakeRequestError(404, "not_found", "intake session not found")
    if session["organization_id"] != auth_context.organization_id:
        raise IntakeRequestError(403, "forbidden", "session belongs to another organization")
    if if_match_version != int(session["version"]):
        raise IntakeRequestError(409, "conflict", "session version mismatch")

    ts = now or datetime.now(timezone.utc)
    answers_patch = payload.get("answers_patch")
    if answers_patch is not None:
        if not isinstance(answers_patch, dict):
            raise IntakeRequestError(422, "validation_error", "answers_patch must be an object")
        session["answers"] = {**session["answers"], **answers_patch}

    if payload.get("current_step") is not None:
        session["current_step"] = str(payload["current_step"])

    if payload.get("status") is not None:
        new_status = str(payload["status"])
        if new_status not in {"in_progress", "completed", "abandoned"}:
            raise IntakeRequestError(422, "validation_error", "invalid intake status")
        if new_status == "completed":
            _validate_completed_answers(
                permit_type=session["permit_type"],
                answers=session["answers"],
            )
            session["completed_at"] = _iso(ts)
            event = _event_envelope(
                event_type="intake.completed",
                aggregate_type="intake_session",
                aggregate_id=session_id,
                organization_id=auth_context.organization_id,
                idempotency_key=f"{session_id}:intake.completed:v1",
                trace_id=trace_id,
                payload={
                    "session_id": session_id,
                    "project_id": session["project_id"],
                    "permit_type": session["permit_type"],
                    "ahj_id": session["ahj_id"],
                },
                produced_by="intake-service",
                occurred_at=ts,
            )
            store.outbox_events.append(event)
        session["status"] = new_status

    session["version"] = int(session["version"]) + 1
    session["updated_at"] = _iso(ts)
    return 200, session


def update_intake_session_persisted(
    *,
    session_id: str,
    if_match_version: int,
    payload: dict[str, object],
    trace_id: str,
    auth_context: AuthContext,
    repository: Stage2Repository,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    session = repository.get_intake_session(session_id)
    if not session:
        raise IntakeRequestError(404, "not_found", "intake session not found")
    if session["organization_id"] != auth_context.organization_id:
        raise IntakeRequestError(403, "forbidden", "session belongs to another organization")
    if if_match_version != int(session["version"]):
        raise IntakeRequestError(409, "conflict", "session version mismatch")

    ts = now or datetime.now(timezone.utc)
    answers_patch = payload.get("answers_patch")
    if answers_patch is not None:
        if not isinstance(answers_patch, dict):
            raise IntakeRequestError(422, "validation_error", "answers_patch must be an object")
        session["answers"] = {**session["answers"], **answers_patch}

    if payload.get("current_step") is not None:
        session["current_step"] = str(payload["current_step"])

    if payload.get("status") is not None:
        new_status = str(payload["status"])
        if new_status not in {"in_progress", "completed", "abandoned"}:
            raise IntakeRequestError(422, "validation_error", "invalid intake status")
        if new_status == "completed":
            _validate_completed_answers(
                permit_type=session["permit_type"],
                answers=session["answers"],
            )
            session["completed_at"] = _iso(ts)
            repository.insert_outbox_event(
                _event_envelope(
                    event_type="intake.completed",
                    aggregate_type="intake_session",
                    aggregate_id=session_id,
                    organization_id=auth_context.organization_id,
                    idempotency_key=f"{session_id}:intake.completed:v1",
                    trace_id=trace_id,
                    payload={
                        "session_id": session_id,
                        "project_id": session["project_id"],
                        "permit_type": session["permit_type"],
                        "ahj_id": session["ahj_id"],
                    },
                    produced_by="intake-service",
                    occurred_at=ts,
                )
            )
        session["status"] = new_status

    session["version"] = int(session["version"]) + 1
    session["updated_at"] = _iso(ts)
    return 200, repository.save_intake_session(session)


def generate_permit_application(
    *,
    permit_id: str,
    intake_session_id: str,
    form_template_id: str,
    mapping_version: int,
    required_mapped_fields: set[str],
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: IntakeStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    if not idempotency_key.strip():
        raise IntakeRequestError(400, "invalid_request", "Idempotency-Key is required")
    session = store.sessions_by_id.get(intake_session_id)
    if not session:
        raise IntakeRequestError(404, "not_found", "intake session not found")
    if session["organization_id"] != auth_context.organization_id:
        raise IntakeRequestError(403, "forbidden", "session belongs to another organization")
    if session["status"] != "completed":
        raise IntakeRequestError(409, "invalid_state", "intake session must be completed")

    required_fields = set(BASE_REQUIRED_FIELDS) | set(PERMIT_SPECIFIC_REQUIRED_FIELDS[session["permit_type"]])
    missing_mappings = sorted(required_fields - required_mapped_fields)
    if missing_mappings:
        raise IntakeRequestError(
            422,
            "validation_error",
            f"missing mapping for required fields: {', '.join(missing_mappings)}",
        )

    key = (auth_context.organization_id, idempotency_key)
    existing_id = store.app_generation_by_org_idempotency.get(key)
    if existing_id:
        return 200, store.applications_by_id[existing_id]

    ts = now or datetime.now(timezone.utc)
    application_id = str(uuid.uuid4())
    application = {
        "application_id": application_id,
        "organization_id": auth_context.organization_id,
        "project_id": session["project_id"],
        "permit_id": permit_id,
        "intake_session_id": intake_session_id,
        "permit_type": session["permit_type"],
        "ahj_id": session["ahj_id"],
        "form_template_id": form_template_id,
        "mapping_version": mapping_version,
        "application_payload": dict(session["answers"]),
        "validation_summary": {"status": "pass", "errors": [], "warnings": []},
        "generated_at": _iso(ts),
    }
    store.applications_by_id[application_id] = application
    store.app_generation_by_org_idempotency[key] = application_id

    event = _event_envelope(
        event_type="permit.application_generated",
        aggregate_type="permit",
        aggregate_id=permit_id,
        organization_id=auth_context.organization_id,
        idempotency_key=f"{idempotency_key}:permit.application_generated:v1",
        trace_id=trace_id,
        payload={
            "permit_id": permit_id,
            "application_id": application_id,
            "form_template_id": form_template_id,
            "mapping_version": mapping_version,
            "generated_at": _iso(ts),
        },
        produced_by="form-service",
        occurred_at=ts,
    )
    store.outbox_events.append(event)
    return 201, application


def generate_permit_application_persisted(
    *,
    permit_id: str,
    intake_session_id: str,
    form_template_id: str,
    mapping_version: int,
    required_mapped_fields: set[str],
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    repository: Stage2Repository,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_write_role(auth_context)
    if not idempotency_key.strip():
        raise IntakeRequestError(400, "invalid_request", "Idempotency-Key is required")
    session = repository.get_intake_session(intake_session_id)
    if not session:
        raise IntakeRequestError(404, "not_found", "intake session not found")
    if session["organization_id"] != auth_context.organization_id:
        raise IntakeRequestError(403, "forbidden", "session belongs to another organization")
    if session["status"] != "completed":
        raise IntakeRequestError(409, "invalid_state", "intake session must be completed")

    required_fields = set(BASE_REQUIRED_FIELDS) | set(PERMIT_SPECIFIC_REQUIRED_FIELDS[session["permit_type"]])
    missing_mappings = sorted(required_fields - required_mapped_fields)
    if missing_mappings:
        raise IntakeRequestError(
            422,
            "validation_error",
            f"missing mapping for required fields: {', '.join(missing_mappings)}",
        )

    ts = now or datetime.now(timezone.utc)
    created, application = repository.create_or_get_permit_application(
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        application={
            "organization_id": auth_context.organization_id,
            "project_id": session["project_id"],
            "permit_id": permit_id,
            "intake_session_id": intake_session_id,
            "permit_type": session["permit_type"],
            "ahj_id": session["ahj_id"],
            "form_template_id": form_template_id,
            "mapping_version": mapping_version,
            "application_payload": dict(session["answers"]),
            "validation_summary": {"status": "pass", "errors": [], "warnings": []},
            "generated_at": _iso(ts),
        },
    )
    if not created:
        return 200, application

    repository.insert_outbox_event(
        _event_envelope(
            event_type="permit.application_generated",
            aggregate_type="permit",
            aggregate_id=permit_id,
            organization_id=auth_context.organization_id,
            idempotency_key=f"{idempotency_key}:permit.application_generated:v1",
            trace_id=trace_id,
            payload={
                "permit_id": permit_id,
                "application_id": application["application_id"],
                "form_template_id": form_template_id,
                "mapping_version": mapping_version,
                "generated_at": _iso(ts),
            },
            produced_by="form-service",
            occurred_at=ts,
        )
    )
    return 201, application
