from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
import uuid

from scripts.stage3.repositories import Stage3Repository

PERMIT_TYPES = {
    "commercial_ti",
    "rooftop_solar",
    "electrical_service_upgrade",
}

AHJ_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")


class PreflightRequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreflightRequest:
    project_id: str
    permit_type: str
    ahj_id: str
    as_of: datetime
    include_recommendations: bool
    include_explainability: bool


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    requester_role: str


def _parse_bool(raw: str | bool | None, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    raise PreflightRequestError(422, "validation_error", "boolean query param is invalid")


def _parse_rfc3339(raw: str) -> datetime:
    try:
        fixed = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(fixed)
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        raise PreflightRequestError(422, "validation_error", "as_of must be RFC3339") from exc


def parse_preflight_request(
    project_id: str,
    query_params: dict[str, str | bool],
    *,
    server_now: datetime,
    project_created_at: datetime,
) -> PreflightRequest:
    try:
        uuid.UUID(project_id)
    except Exception as exc:  # noqa: BLE001
        raise PreflightRequestError(422, "validation_error", "projectId must be a valid UUID") from exc

    permit_type = str(query_params.get("permit_type") or "").strip()
    if not permit_type:
        raise PreflightRequestError(400, "invalid_request", "permit_type is required")
    if permit_type not in PERMIT_TYPES:
        raise PreflightRequestError(422, "validation_error", "unsupported permit_type")

    ahj_id = str(query_params.get("ahj_id") or "").strip()
    if not ahj_id:
        raise PreflightRequestError(400, "invalid_request", "ahj_id is required")
    if not AHJ_ID_RE.match(ahj_id):
        raise PreflightRequestError(422, "validation_error", "ahj_id format is invalid")

    as_of_raw = query_params.get("as_of")
    as_of = _parse_rfc3339(str(as_of_raw)) if as_of_raw else server_now.astimezone(timezone.utc)

    project_created_utc = project_created_at.astimezone(timezone.utc)
    if as_of < project_created_utc:
        raise PreflightRequestError(
            422,
            "validation_error",
            "as_of must be greater than or equal to project creation time",
        )

    if as_of > server_now.astimezone(timezone.utc) + timedelta(minutes=5):
        raise PreflightRequestError(
            422,
            "validation_error",
            "as_of exceeds allowed future clock-skew window",
        )

    include_recommendations = _parse_bool(query_params.get("include_recommendations"), default=True)
    include_explainability = _parse_bool(query_params.get("include_explainability"), default=True)

    return PreflightRequest(
        project_id=project_id,
        permit_type=permit_type,
        ahj_id=ahj_id,
        as_of=as_of,
        include_recommendations=include_recommendations,
        include_explainability=include_explainability,
    )


def _score_band(score: float) -> str:
    if score < 0.25:
        return "low"
    if score < 0.5:
        return "medium"
    if score < 0.75:
        return "high"
    return "critical"


def _deterministic_score(project_id: str, permit_type: str, ahj_id: str, as_of: datetime) -> float:
    seed = f"{project_id}|{permit_type}|{ahj_id}|{as_of.isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 10001) / 10000.0


def get_preflight_risk(
    project_id: str,
    query_params: dict[str, str | bool],
    *,
    auth_context: AuthContext,
    project_record: dict[str, object],
    server_now: datetime | None = None,
) -> tuple[int, dict[str, object]]:
    now = server_now or datetime.now(timezone.utc)

    project_org_id = str(project_record.get("organization_id") or "")
    if project_org_id != auth_context.organization_id:
        raise PreflightRequestError(403, "forbidden", "project does not belong to caller organization")

    created_at = project_record.get("created_at")
    if not isinstance(created_at, datetime):
        raise PreflightRequestError(500, "internal_error", "project created_at is missing")

    req = parse_preflight_request(
        project_id,
        query_params,
        server_now=now,
        project_created_at=created_at,
    )

    risk_score = _deterministic_score(req.project_id, req.permit_type, req.ahj_id, req.as_of)
    response: dict[str, object] = {
        "project_id": req.project_id,
        "permit_type": req.permit_type,
        "ahj_id": req.ahj_id,
        "risk_score": risk_score,
        "risk_band": _score_band(risk_score),
        "confidence_score": 0.82,
        "model_version": "stage3-baseline-v1",
        "scored_at": req.as_of.isoformat(),
    }

    if req.include_explainability:
        response["top_risk_factors"] = [
            {
                "factor_code": "ahj_cycle_variance",
                "factor_label": "AHJ correction-cycle variance",
                "contribution": 0.41,
                "evidence_ref_ids": ["ev_ahj_hist_001"],
            },
            {
                "factor_code": "submission_completeness",
                "factor_label": "Submission completeness",
                "contribution": 0.29,
                "evidence_ref_ids": ["ev_pkg_002"],
            },
            {
                "factor_code": "permit_complexity",
                "factor_label": "Permit complexity",
                "contribution": 0.17,
                "evidence_ref_ids": ["ev_scope_003"],
            },
        ]

    if req.include_recommendations:
        response["recommended_actions"] = [
            {
                "action_id": "act_missing_structural_notes",
                "action_text": "Attach structural notes addendum before submission.",
                "expected_impact": "Reduce first-cycle correction probability.",
                "priority": "high",
                "owner_role": "pm",
            }
        ]

    return 200, response


def get_preflight_risk_persisted(
    project_id: str,
    query_params: dict[str, str | bool],
    *,
    auth_context: AuthContext,
    project_record: dict[str, object],
    repository: Stage3Repository,
    server_now: datetime | None = None,
) -> tuple[int, dict[str, object]]:
    status, payload = get_preflight_risk(
        project_id,
        query_params,
        auth_context=auth_context,
        project_record=project_record,
        server_now=server_now,
    )
    repository.insert_preflight_score(
        {
            "organization_id": auth_context.organization_id,
            "project_id": payload["project_id"],
            "permit_id": project_record.get("permit_id"),
            "ahj_id": payload["ahj_id"],
            "permit_type": payload["permit_type"],
            "score": payload["risk_score"],
            "band": payload["risk_band"],
            "confidence_score": payload["confidence_score"],
            "model_version": payload["model_version"],
            "scored_at": payload["scored_at"],
        }
    )
    return status, payload
