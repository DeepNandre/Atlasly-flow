from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import uuid

from scripts.stage3.repositories import Stage3Repository


ALLOWED_FINANCE_ROLES = {"owner", "admin"}
ALLOWED_MILESTONE_STATES = {"payout_eligible"}
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

ALLOWED_INSTRUCTION_TRANSITIONS = {
    "created": {"submitted", "failed_transient", "failed_terminal"},
    "submitted": {"settled", "failed_transient", "failed_terminal", "reversed"},
    "failed_transient": {"submitted", "failed_terminal"},
    "failed_terminal": set(),
    "settled": {"reversed"},
    "reversed": set(),
}


class PayoutRequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    requester_role: str


@dataclass
class PayoutStore:
    instructions_by_id: dict[str, dict]
    instruction_id_by_idempotency: dict[tuple[str, str], str]
    outbox_events: list[dict]

    @classmethod
    def empty(cls) -> "PayoutStore":
        return cls({}, {}, [])


def _event_envelope(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    organization_id: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": occurred_at.isoformat(),
        "produced_by": "payout-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def create_payout_instruction(
    *,
    milestone: dict,
    amount: float,
    currency: str,
    beneficiary_id: str,
    provider: str,
    idempotency_key: str,
    trace_id: str,
    step_up_authenticated: bool,
    auth_context: AuthContext,
    store: PayoutStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ts = now or datetime.now(timezone.utc)

    if auth_context.requester_role not in ALLOWED_FINANCE_ROLES:
        raise PayoutRequestError(403, "forbidden", "role cannot initiate payout actions")

    if not step_up_authenticated:
        raise PayoutRequestError(401, "step_up_required", "step-up authentication is required")

    milestone_org = str(milestone.get("organization_id") or "")
    if milestone_org != auth_context.organization_id:
        raise PayoutRequestError(403, "forbidden", "milestone belongs to another organization")

    milestone_state = str(milestone.get("milestone_state") or "")
    if milestone_state not in ALLOWED_MILESTONE_STATES:
        raise PayoutRequestError(409, "invalid_state", "milestone is not payout_eligible")

    if amount <= 0:
        raise PayoutRequestError(422, "validation_error", "amount must be greater than zero")

    if not CURRENCY_RE.match(currency):
        raise PayoutRequestError(422, "validation_error", "currency must be 3-letter ISO code")

    if not idempotency_key.strip():
        raise PayoutRequestError(400, "invalid_request", "idempotency_key is required")

    if not trace_id.strip():
        raise PayoutRequestError(400, "invalid_request", "trace_id is required")

    key = (auth_context.organization_id, idempotency_key)
    existing_id = store.instruction_id_by_idempotency.get(key)
    if existing_id:
        return 200, store.instructions_by_id[existing_id]

    instruction_id = str(uuid.uuid4())
    record = {
        "instruction_id": instruction_id,
        "organization_id": auth_context.organization_id,
        "milestone_id": milestone["id"],
        "permit_id": milestone["permit_id"],
        "project_id": milestone["project_id"],
        "beneficiary_id": beneficiary_id,
        "amount": round(amount, 2),
        "currency": currency,
        "provider": provider,
        "instruction_state": "created",
        "idempotency_key": idempotency_key,
        "created_at": ts.isoformat(),
        "updated_at": ts.isoformat(),
    }

    store.instructions_by_id[instruction_id] = record
    store.instruction_id_by_idempotency[key] = instruction_id

    event = _event_envelope(
        event_type="payout.instruction_created",
        aggregate_type="payout_instruction",
        aggregate_id=instruction_id,
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        payload={
            "instruction_id": instruction_id,
            "milestone_id": milestone["id"],
            "permit_id": milestone["permit_id"],
            "project_id": milestone["project_id"],
            "amount": round(amount, 2),
            "currency": currency,
            "beneficiary_id": beneficiary_id,
            "provider": provider,
            "instruction_status": "created",
            "created_at": ts.isoformat(),
        },
        occurred_at=ts,
    )
    store.outbox_events.append(event)

    return 201, record


def transition_instruction_state(
    *,
    instruction_id: str,
    new_state: str,
    store: PayoutStore,
    now: datetime | None = None,
) -> dict:
    record = store.instructions_by_id.get(instruction_id)
    if not record:
        raise PayoutRequestError(404, "not_found", "instruction does not exist")

    current = record["instruction_state"]
    allowed = ALLOWED_INSTRUCTION_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise PayoutRequestError(
            409,
            "invalid_state_transition",
            f"cannot transition instruction from {current} to {new_state}",
        )

    ts = now or datetime.now(timezone.utc)
    record["instruction_state"] = new_state
    record["updated_at"] = ts.isoformat()
    return record


def transition_instruction_state_persisted(
    *,
    organization_id: str,
    instruction_id: str,
    new_state: str,
    repository,
    now: datetime | None = None,
) -> dict:
    record = repository.get_payout_instruction(
        organization_id=organization_id,
        instruction_id=instruction_id,
    )
    if not record:
        raise PayoutRequestError(404, "not_found", "instruction does not exist")

    current = record["instruction_state"]
    allowed = ALLOWED_INSTRUCTION_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise PayoutRequestError(
            409,
            "invalid_state_transition",
            f"cannot transition instruction from {current} to {new_state}",
        )

    ts = now or datetime.now(timezone.utc)
    return repository.update_payout_instruction_state(
        organization_id=organization_id,
        instruction_id=instruction_id,
        new_state=new_state,
        updated_at=ts.isoformat(),
    )


def create_payout_instruction_persisted(
    *,
    milestone: dict,
    amount: float,
    currency: str,
    beneficiary_id: str,
    provider: str,
    idempotency_key: str,
    trace_id: str,
    step_up_authenticated: bool,
    auth_context: AuthContext,
    repository: Stage3Repository,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ts = now or datetime.now(timezone.utc)

    if auth_context.requester_role not in ALLOWED_FINANCE_ROLES:
        raise PayoutRequestError(403, "forbidden", "role cannot initiate payout actions")
    if not step_up_authenticated:
        raise PayoutRequestError(401, "step_up_required", "step-up authentication is required")

    milestone_org = str(milestone.get("organization_id") or "")
    if milestone_org != auth_context.organization_id:
        raise PayoutRequestError(403, "forbidden", "milestone belongs to another organization")
    milestone_state = str(milestone.get("milestone_state") or "")
    if milestone_state not in ALLOWED_MILESTONE_STATES:
        raise PayoutRequestError(409, "invalid_state", "milestone is not payout_eligible")

    if amount <= 0:
        raise PayoutRequestError(422, "validation_error", "amount must be greater than zero")
    if not CURRENCY_RE.match(currency):
        raise PayoutRequestError(422, "validation_error", "currency must be 3-letter ISO code")
    if not idempotency_key.strip():
        raise PayoutRequestError(400, "invalid_request", "idempotency_key is required")
    if not trace_id.strip():
        raise PayoutRequestError(400, "invalid_request", "trace_id is required")

    instruction_id = str(uuid.uuid4())
    instruction = {
        "instruction_id": instruction_id,
        "organization_id": auth_context.organization_id,
        "milestone_id": milestone["id"],
        "permit_id": milestone["permit_id"],
        "project_id": milestone["project_id"],
        "beneficiary_id": beneficiary_id,
        "amount": round(amount, 2),
        "currency": currency,
        "provider": provider,
        "instruction_state": "created",
        "idempotency_key": idempotency_key,
        "created_at": ts.isoformat(),
        "updated_at": ts.isoformat(),
    }
    event = _event_envelope(
        event_type="payout.instruction_created",
        aggregate_type="payout_instruction",
        aggregate_id=instruction_id,
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        payload={
            "instruction_id": instruction_id,
            "milestone_id": milestone["id"],
            "permit_id": milestone["permit_id"],
            "project_id": milestone["project_id"],
            "amount": round(amount, 2),
            "currency": currency,
            "beneficiary_id": beneficiary_id,
            "provider": provider,
            "instruction_status": "created",
            "created_at": ts.isoformat(),
        },
        occurred_at=ts,
    )

    created, record = repository.create_instruction_with_outbox(
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        instruction=instruction,
        event=event,
    )
    if not created:
        return 200, record

    return 201, record
