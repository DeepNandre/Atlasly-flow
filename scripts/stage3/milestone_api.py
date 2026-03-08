from __future__ import annotations

from datetime import datetime, timezone
import uuid

from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError


ALLOWED_VERIFY_ROLES = {"owner", "admin", "pm"}
ALLOWED_VERIFY_SOURCE = {"connector_event", "manual_override"}
VERIFY_FROM_STATES = {"draft", "pending_verification"}

REQUIRED_EVIDENCE_KEYS = {
    "permit_event_ids",
    "raw_source_ref",
    "occurred_at",
    "received_at",
}


def _event_envelope(
    *,
    organization_id: str,
    idempotency_key: str,
    trace_id: str,
    milestone_id: str,
    payload: dict,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "milestone.verified",
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": "milestone",
        "aggregate_id": milestone_id,
        "occurred_at": occurred_at.isoformat(),
        "produced_by": "milestone-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def verify_milestone(
    *,
    milestone: dict,
    verification_source: str,
    evidence: dict,
    verification_rule_version: str,
    trace_id: str,
    idempotency_key: str,
    auth_context: AuthContext,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    ts = now or datetime.now(timezone.utc)

    if auth_context.requester_role not in ALLOWED_VERIFY_ROLES:
        raise PayoutRequestError(403, "forbidden", "role cannot verify milestones")

    milestone_org = str(milestone.get("organization_id") or "")
    if milestone_org != auth_context.organization_id:
        raise PayoutRequestError(403, "forbidden", "milestone belongs to another organization")

    if verification_source not in ALLOWED_VERIFY_SOURCE:
        raise PayoutRequestError(422, "validation_error", "verification_source is invalid")

    current_state = str(milestone.get("milestone_state") or "")
    if current_state not in VERIFY_FROM_STATES:
        raise PayoutRequestError(
            409,
            "invalid_state",
            f"milestone cannot be verified from state {current_state}",
        )

    if not verification_rule_version.strip():
        raise PayoutRequestError(400, "invalid_request", "verification_rule_version is required")

    if not trace_id.strip():
        raise PayoutRequestError(400, "invalid_request", "trace_id is required")

    if not idempotency_key.strip():
        raise PayoutRequestError(400, "invalid_request", "idempotency_key is required")

    missing = [key for key in REQUIRED_EVIDENCE_KEYS if key not in evidence]
    if missing:
        raise PayoutRequestError(
            422,
            "validation_error",
            f"evidence is missing required keys: {', '.join(sorted(missing))}",
        )

    if not isinstance(evidence.get("permit_event_ids"), list) or not evidence["permit_event_ids"]:
        raise PayoutRequestError(422, "validation_error", "permit_event_ids must be a non-empty list")

    updated = dict(milestone)
    updated["milestone_state"] = "verified"
    updated["verified_at"] = ts.isoformat()
    updated["verification_source"] = verification_source
    updated["verification_rule_version"] = verification_rule_version
    updated["evidence_payload"] = evidence
    updated["verified_by"] = auth_context.requester_role

    event = _event_envelope(
        organization_id=auth_context.organization_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        milestone_id=updated["id"],
        payload={
            "milestone_id": updated["id"],
            "permit_id": updated["permit_id"],
            "project_id": updated["project_id"],
            "verification_source": verification_source,
            "verified_at": updated["verified_at"],
            "verification_rule_version": verification_rule_version,
            "evidence_refs": evidence.get("permit_event_ids", []),
            "verified_by": auth_context.requester_role,
        },
        occurred_at=ts,
    )
    return updated, event


def verify_milestone_persisted(
    *,
    milestone: dict,
    verification_source: str,
    evidence: dict,
    verification_rule_version: str,
    trace_id: str,
    idempotency_key: str,
    auth_context: AuthContext,
    repository,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    updated, event = verify_milestone(
        milestone=milestone,
        verification_source=verification_source,
        evidence=evidence,
        verification_rule_version=verification_rule_version,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        auth_context=auth_context,
        now=now,
    )
    repository.insert_outbox_event(event)
    return updated, event
