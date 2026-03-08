from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import uuid

FEEDBACK_REASON_CODES = {
    "WRONG_DISCIPLINE",
    "WRONG_TRADE_PARTNER",
    "WRONG_PROJECT_ROLE",
    "ASSIGNEE_UNAVAILABLE",
    "MISSING_RULE",
    "RULE_PRIORITY_ISSUE",
    "TEMP_CAPACITY_REDIRECT",
    "OTHER_VERIFIED",
}


class Stage1BRequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CreateTasksRequest:
    letter_id: str
    approved_extraction_ids: tuple[str, ...]
    dry_run: bool
    idempotency_key: str
    request_hash: str


def _assert_uuid(raw: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except Exception as exc:  # noqa: BLE001
        raise Stage1BRequestError(422, "validation_error", f"{field_name} must be a valid UUID") from exc


def _canonical_json(data: dict[str, object]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def build_server_idempotency_key(
    organization_id: str,
    project_id: str,
    letter_id: str,
    approved_extraction_ids: list[str],
    letter_version_hash: str,
) -> str:
    org = _assert_uuid(organization_id, "organization_id")
    project = _assert_uuid(project_id, "project_id")
    letter = _assert_uuid(letter_id, "letter_id")

    normalized_ids = sorted({_assert_uuid(v, "approved_extraction_id") for v in approved_extraction_ids})
    if not normalized_ids:
        raise Stage1BRequestError(422, "validation_error", "approved_extraction_ids must include at least one item")

    seed = f"{org}|{project}|{letter}|{','.join(normalized_ids)}|{letter_version_hash}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"gen:{org}:{project}:{letter}:{digest[:24]}"


def parse_create_tasks_request(
    *,
    organization_id: str,
    project_id: str,
    letter_id: str,
    body: dict[str, object] | None,
    client_idempotency_key: str | None,
    letter_version_hash: str,
) -> CreateTasksRequest:
    normalized_letter_id = _assert_uuid(letter_id, "letter_id")
    payload = body or {}

    approved_ids_raw = payload.get("approved_extraction_ids")
    if approved_ids_raw is None:
        raise Stage1BRequestError(422, "validation_error", "approved_extraction_ids is required")
    if not isinstance(approved_ids_raw, list) or not approved_ids_raw:
        raise Stage1BRequestError(422, "validation_error", "approved_extraction_ids must be a non-empty array")

    approved_ids = tuple(sorted({_assert_uuid(str(v), "approved_extraction_id") for v in approved_ids_raw}))
    dry_run_raw = payload.get("dry_run", False)
    if not isinstance(dry_run_raw, bool):
        raise Stage1BRequestError(422, "validation_error", "dry_run must be boolean")

    idempotency_key = (client_idempotency_key or "").strip()
    if not idempotency_key:
        idempotency_key = build_server_idempotency_key(
            organization_id=organization_id,
            project_id=project_id,
            letter_id=normalized_letter_id,
            approved_extraction_ids=list(approved_ids),
            letter_version_hash=letter_version_hash,
        )

    request_hash = hashlib.sha256(
        _canonical_json(
            {
                "letter_id": normalized_letter_id,
                "approved_extraction_ids": approved_ids,
                "dry_run": dry_run_raw,
            }
        ).encode("utf-8")
    ).hexdigest()

    return CreateTasksRequest(
        letter_id=normalized_letter_id,
        approved_extraction_ids=approved_ids,
        dry_run=dry_run_raw,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )


def evaluate_idempotent_replay(
    *,
    existing_run_status: str | None,
    existing_request_hash: str | None,
    incoming_request_hash: str,
) -> tuple[int, str]:
    """
    Returns (http_status, semantic_outcome):
      - (201, "create") for first-time execution
      - (200, "replay") for exact idempotent replay
      - (409, "conflict") for same key + different request hash
    """
    if existing_run_status is None:
        return 201, "create"

    if existing_request_hash == incoming_request_hash and existing_run_status == "COMPLETED":
        return 200, "replay"

    return 409, "conflict"


def validate_reassignment_payload(payload: dict[str, object]) -> None:
    from_assignee_id = _assert_uuid(str(payload.get("from_assignee_id") or ""), "from_assignee_id")
    to_assignee_id = _assert_uuid(str(payload.get("to_assignee_id") or ""), "to_assignee_id")

    if from_assignee_id == to_assignee_id:
        raise Stage1BRequestError(422, "validation_error", "from_assignee_id and to_assignee_id must differ")

    reason_code = str(payload.get("feedback_reason_code") or "").strip()
    if reason_code not in FEEDBACK_REASON_CODES:
        raise Stage1BRequestError(422, "validation_error", "feedback_reason_code is invalid")

    if "source_confidence" in payload and payload["source_confidence"] is not None:
        try:
            conf = float(payload["source_confidence"])
        except Exception as exc:  # noqa: BLE001
            raise Stage1BRequestError(422, "validation_error", "source_confidence must be numeric") from exc
        if conf < 0 or conf > 1:
            raise Stage1BRequestError(422, "validation_error", "source_confidence must be between 0 and 1")
