from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from scripts.stage2.status_sync import AuthContext
from scripts.stage2.status_sync import Stage2SyncError
from scripts.stage2.status_sync import SyncStore
from scripts.stage2.status_sync import create_poll_run
from scripts.stage2.repositories import Stage2Repository

AHJ_ID_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")


def _parse_bool(raw: object, *, default: bool) -> bool:
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
    raise Stage2SyncError(422, "validation_error", "boolean field is invalid")


def _parse_rfc3339(raw: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        raise Stage2SyncError(422, "validation_error", f"{field_name} must be RFC3339") from exc


def post_connector_poll(
    *,
    ahj: str,
    request_body: dict[str, object] | None,
    idempotency_key: str,
    auth_context: AuthContext,
    store: SyncStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ahj_id = ahj.strip().lower()
    if not ahj_id:
        raise Stage2SyncError(400, "invalid_request", "ahj path parameter is required")
    if not AHJ_ID_RE.match(ahj_id):
        raise Stage2SyncError(422, "validation_error", "ahj path format is invalid")
    if not idempotency_key.strip():
        raise Stage2SyncError(400, "invalid_request", "Idempotency-Key is required")
    if not request_body:
        raise Stage2SyncError(422, "validation_error", "request body is required")

    connector = str(request_body.get("connector") or "").strip()
    if not connector:
        raise Stage2SyncError(422, "validation_error", "connector is required")

    dry_run = _parse_bool(request_body.get("dry_run"), default=False)
    force = _parse_bool(request_body.get("force"), default=False)

    return create_poll_run(
        connector=connector,
        ahj_id=ahj_id,
        idempotency_key=idempotency_key,
        auth_context=auth_context,
        store=store,
        dry_run=dry_run,
        force=force,
        now=now,
    )


def post_connector_poll_persisted(
    *,
    ahj: str,
    request_body: dict[str, object] | None,
    idempotency_key: str,
    auth_context: AuthContext,
    repository: Stage2Repository,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ahj_id = ahj.strip().lower()
    if not ahj_id:
        raise Stage2SyncError(400, "invalid_request", "ahj path parameter is required")
    if not AHJ_ID_RE.match(ahj_id):
        raise Stage2SyncError(422, "validation_error", "ahj path format is invalid")
    if not idempotency_key.strip():
        raise Stage2SyncError(400, "invalid_request", "Idempotency-Key is required")
    if not request_body:
        raise Stage2SyncError(422, "validation_error", "request body is required")

    connector = str(request_body.get("connector") or "").strip()
    if not connector:
        raise Stage2SyncError(422, "validation_error", "connector is required")

    dry_run = _parse_bool(request_body.get("dry_run"), default=False)
    force = _parse_bool(request_body.get("force"), default=False)
    ts = now or datetime.now(timezone.utc)

    created, run = repository.create_or_get_poll_run(
        organization_id=auth_context.organization_id,
        connector=connector,
        ahj_id=ahj_id,
        idempotency_key=idempotency_key,
        run={
            "organization_id": auth_context.organization_id,
            "connector": connector,
            "ahj_id": ahj_id,
            "status": "running",
            "run_started_at": ts.isoformat(),
            "dry_run": dry_run,
            "force": force,
        },
    )
    return (202 if created else 200), run


def get_status_timeline(
    *,
    permit_id: str,
    query_params: dict[str, object] | None,
    auth_context: AuthContext,
    store: SyncStore,
) -> tuple[int, dict]:
    try:
        uuid.UUID(permit_id)
    except Exception as exc:  # noqa: BLE001
        raise Stage2SyncError(422, "validation_error", "permitId must be a valid UUID") from exc

    qp = query_params or {}
    limit_raw = qp.get("limit", 100)
    try:
        limit = int(limit_raw)
    except Exception as exc:  # noqa: BLE001
        raise Stage2SyncError(422, "validation_error", "limit must be an integer") from exc
    if limit < 1 or limit > 200:
        raise Stage2SyncError(422, "validation_error", "limit must be between 1 and 200")

    from_ts = _parse_rfc3339(str(qp["from"]), field_name="from") if qp.get("from") else None
    to_ts = _parse_rfc3339(str(qp["to"]), field_name="to") if qp.get("to") else None
    if from_ts and to_ts and from_ts > to_ts:
        raise Stage2SyncError(422, "validation_error", "from must be less than or equal to to")

    permit_org = store.permit_org_by_id.get(permit_id)
    if permit_org and permit_org != auth_context.organization_id:
        raise Stage2SyncError(403, "forbidden", "permit belongs to another organization")

    filtered = []
    for event in store.status_events:
        if event["permit_id"] != permit_id:
            continue
        if event["organization_id"] != auth_context.organization_id:
            continue
        if event["normalized_status"] is None:
            continue
        observed_at = _parse_rfc3339(str(event["observed_at"]), field_name="observed_at")
        if from_ts and observed_at < from_ts:
            continue
        if to_ts and observed_at > to_ts:
            continue
        prov = store.provenance_by_event_id.get(event["id"], {})
        filtered.append(
            {
                "event_id": event["id"],
                "observed_at": event["observed_at"],
                "raw_status": event["raw_status"],
                "normalized_status": event["normalized_status"],
                "confidence": event["confidence"],
                "source": event["source"],
                "provenance": {
                    "source_type": prov.get("source_type", "manual"),
                    "source_ref": prov.get("source_ref", "unknown"),
                    "source_payload_hash": prov.get("source_payload_hash", event["event_hash"]),
                },
                "parser_version": event.get("parser_version"),
            }
        )

    if not filtered and not permit_org:
        raise Stage2SyncError(404, "not_found", "permit not found")

    filtered.sort(key=lambda item: item["observed_at"], reverse=True)
    return 200, {
        "permit_id": permit_id,
        "timeline": filtered[:limit],
    }


def get_status_timeline_persisted(
    *,
    permit_id: str,
    query_params: dict[str, object] | None,
    auth_context: AuthContext,
    repository: Stage2Repository,
) -> tuple[int, dict]:
    try:
        uuid.UUID(permit_id)
    except Exception as exc:  # noqa: BLE001
        raise Stage2SyncError(422, "validation_error", "permitId must be a valid UUID") from exc

    qp = query_params or {}
    limit_raw = qp.get("limit", 100)
    try:
        limit = int(limit_raw)
    except Exception as exc:  # noqa: BLE001
        raise Stage2SyncError(422, "validation_error", "limit must be an integer") from exc
    if limit < 1 or limit > 200:
        raise Stage2SyncError(422, "validation_error", "limit must be between 1 and 200")

    from_ts = _parse_rfc3339(str(qp["from"]), field_name="from") if qp.get("from") else None
    to_ts = _parse_rfc3339(str(qp["to"]), field_name="to") if qp.get("to") else None
    if from_ts and to_ts and from_ts > to_ts:
        raise Stage2SyncError(422, "validation_error", "from must be less than or equal to to")

    projection = repository.get_status_projection(permit_id)
    if projection and projection["organization_id"] != auth_context.organization_id:
        raise Stage2SyncError(403, "forbidden", "permit belongs to another organization")

    events = repository.list_status_events_by_permit(
        organization_id=auth_context.organization_id,
        permit_id=permit_id,
    )
    if not events and not projection:
        raise Stage2SyncError(404, "not_found", "permit not found")

    filtered = []
    for event in events:
        if event["normalized_status"] is None:
            continue
        observed_at = _parse_rfc3339(str(event["observed_at"]), field_name="observed_at")
        if from_ts and observed_at < from_ts:
            continue
        if to_ts and observed_at > to_ts:
            continue
        prov = repository.get_status_provenance(event["id"]) or {}
        filtered.append(
            {
                "event_id": event["id"],
                "observed_at": event["observed_at"],
                "raw_status": event["raw_status"],
                "normalized_status": event["normalized_status"],
                "confidence": event["confidence"],
                "source": event["source"],
                "provenance": {
                    "source_type": prov.get("source_type", "manual"),
                    "source_ref": prov.get("source_ref", "unknown"),
                    "source_payload_hash": prov.get("source_payload_hash", event["event_hash"]),
                },
                "parser_version": event.get("parser_version"),
            }
        )
    return 200, {"permit_id": permit_id, "timeline": filtered[:limit]}
