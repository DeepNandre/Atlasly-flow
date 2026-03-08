from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import uuid

from scripts.stage2.repositories import Stage2Repository

CANONICAL_STATUSES = {
    "submitted",
    "in_review",
    "corrections_required",
    "approved",
    "issued",
    "expired",
}
CONNECTORS = {"accela_api", "opengov_api", "cloudpermit_portal_runner"}
POLL_TRIGGER_ROLES = {"owner", "admin", "pm"}
AUTO_APPLY_CONFIDENCE_THRESHOLD = 0.90

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"in_review", "corrections_required", "approved", "issued"},
    "in_review": {"corrections_required", "approved", "issued"},
    "corrections_required": {"submitted", "in_review", "approved"},
    "approved": {"issued", "expired"},
    "issued": {"expired"},
    "expired": set(),
}

LEXICAL_RULES = [
    ("submitted", ["submitted", "application received", "intake complete", "pending intake review"]),
    ("in_review", ["under review", "plan review", "department review", "routing"]),
    ("corrections_required", ["revisions required", "resubmit", "denied with corrections", "hold for corrections"]),
    ("approved", ["approved", "approved pending issuance", "ready to issue"]),
    ("issued", ["issued", "permit issued", "finalized/issued"]),
    ("expired", ["expired", "void", "closed expired"]),
]


class Stage2SyncError(Exception):
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
class SyncStore:
    poll_runs_by_key: dict[tuple[str, str, str, str], dict]
    poll_runs_by_id: dict[str, dict]
    status_events: list[dict]
    transition_reviews: list[dict]
    provenance_by_event_id: dict[str, dict]
    permit_org_by_id: dict[str, str]
    permit_current_status: dict[str, str]

    @classmethod
    def empty(cls) -> "SyncStore":
        return cls({}, {}, [], [], {}, {}, {})


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def create_poll_run(
    *,
    connector: str,
    ahj_id: str,
    idempotency_key: str,
    auth_context: AuthContext,
    store: SyncStore,
    dry_run: bool = False,
    force: bool = False,
    now: datetime | None = None,
) -> tuple[int, dict]:
    ts = now or datetime.now(timezone.utc)
    if connector not in CONNECTORS:
        raise Stage2SyncError(422, "validation_error", "unsupported connector")
    if auth_context.requester_role not in POLL_TRIGGER_ROLES:
        raise Stage2SyncError(403, "forbidden", "role cannot trigger connector polls")

    run_key = (auth_context.organization_id, connector, ahj_id, idempotency_key)
    existing = store.poll_runs_by_key.get(run_key)
    if existing:
        return 200, existing

    run = {
        "run_id": str(uuid.uuid4()),
        "organization_id": auth_context.organization_id,
        "connector": connector,
        "ahj_id": ahj_id,
        "status": "running",
        "run_started_at": _iso(ts),
        "dry_run": dry_run,
        "force": force,
    }
    store.poll_runs_by_key[run_key] = run
    store.poll_runs_by_id[run["run_id"]] = run
    return 202, run


def normalize_status(
    *,
    raw_status: str,
    connector: str | None = None,
    ahj_id: str | None = None,
    rules: list[dict] | None = None,
) -> dict:
    normalized_raw = raw_status.strip().lower()
    active_rules = sorted(
        [
            r
            for r in (rules or [])
            if r.get("is_active", True)
            and (r.get("connector") in {None, connector})
            and (r.get("ahj_id") in {None, ahj_id})
        ],
        key=lambda r: int(r.get("priority", 100)),
    )

    for rule in active_rules:
        match_type = rule.get("match_type", "regex")
        pattern = str(rule.get("raw_pattern", "")).strip().lower()
        if not pattern:
            continue
        matched = False
        if match_type == "exact":
            matched = normalized_raw == pattern
        elif match_type == "regex":
            matched = re.search(pattern, normalized_raw) is not None
        elif match_type == "lexical":
            matched = pattern in normalized_raw
        if matched:
            return {
                "normalized_status": rule["normalized_status"],
                "confidence": float(rule.get("confidence_score", 0.95)),
                "strategy": match_type,
            }

    lexical_matches: set[str] = set()
    for status, keywords in LEXICAL_RULES:
        for keyword in keywords:
            if keyword in normalized_raw:
                lexical_matches.add(status)
                break

    if not lexical_matches:
        return {"normalized_status": None, "confidence": 0.0, "strategy": "unmapped"}

    picked = sorted(lexical_matches)[0]
    confidence = 0.75
    if len(lexical_matches) > 1:
        confidence = max(0.0, confidence - 0.20)
    return {"normalized_status": picked, "confidence": confidence, "strategy": "lexical"}


def is_valid_transition(old_status: str, new_status: str) -> bool:
    allowed = ALLOWED_TRANSITIONS.get(old_status)
    if allowed is None:
        return False
    return new_status in allowed


def classify_drift(
    *,
    projected_status: str,
    recomputed_status: str,
    previous_ruleset_version: str,
    current_ruleset_version: str,
    previous_payload_hash: str | None,
    current_payload_hash: str | None,
) -> str | None:
    if projected_status == recomputed_status:
        return None
    if previous_ruleset_version != current_ruleset_version:
        return "mapping_drift"
    if previous_payload_hash and current_payload_hash and previous_payload_hash != current_payload_hash:
        return "source_drift"
    return "timeline_gap"


def build_status_observed_event(
    *,
    organization_id: str,
    permit_id: str,
    raw_status: str,
    normalized_status: str,
    source: str,
    confidence: float,
    observed_at: datetime,
    trace_id: str,
    idempotency_key: str,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "permit.status_observed",
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": "permit",
        "aggregate_id": permit_id,
        "occurred_at": _iso(observed_at),
        "produced_by": "connector-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": {
            "permit_id": permit_id,
            "raw_status": raw_status,
            "normalized_status": normalized_status,
            "source": source,
            "confidence": confidence,
            "observed_at": _iso(observed_at),
        },
    }


def build_status_changed_event(
    *,
    organization_id: str,
    permit_id: str,
    old_status: str,
    new_status: str,
    source_event_id: str,
    trace_id: str,
    idempotency_key: str,
    occurred_at: datetime,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "permit.status_changed",
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": "permit",
        "aggregate_id": permit_id,
        "occurred_at": _iso(occurred_at),
        "produced_by": "permit-service",
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": {
            "permit_id": permit_id,
            "old_status": old_status,
            "new_status": new_status,
            "source_event_id": source_event_id,
        },
    }


def _build_manual_review(
    *,
    organization_id: str,
    permit_id: str,
    status_event_id: str,
    from_status: str | None,
    to_status: str | None,
    rejection_reason: str,
    observed_at: datetime,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "permit_id": permit_id,
        "status_event_id": status_event_id,
        "from_status": from_status,
        "to_status": to_status,
        "rejection_reason": rejection_reason,
        "resolution_state": "open",
        "created_at": _iso(observed_at),
    }


def record_status_observation(
    *,
    permit_id: str,
    source: str,
    raw_status: str,
    old_status: str | None,
    organization_id: str,
    connector: str,
    ahj_id: str,
    observed_at: datetime,
    parser_version: str,
    event_hash: str,
    trace_id: str,
    idempotency_key: str,
    rules: list[dict] | None,
    provenance_source_type: str = "api",
    provenance_source_ref: str | None = None,
    source_payload_hash: str | None = None,
    store: SyncStore,
) -> dict:
    normalized = normalize_status(
        raw_status=raw_status,
        connector=connector,
        ahj_id=ahj_id,
        rules=rules,
    )
    event = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "permit_id": permit_id,
        "raw_status": raw_status,
        "normalized_status": normalized["normalized_status"],
        "source": source,
        "confidence": normalized["confidence"],
        "observed_at": _iso(observed_at),
        "parser_version": parser_version,
        "event_hash": event_hash,
    }
    store.status_events.append(event)
    store.permit_org_by_id[permit_id] = organization_id

    provenance = {
        "source_type": provenance_source_type,
        "source_ref": provenance_source_ref or f"{connector}:{source}",
        "source_payload_hash": source_payload_hash or event_hash,
        "parser_version": parser_version,
        "ingested_at": _iso(observed_at),
    }
    store.provenance_by_event_id[event["id"]] = provenance

    inferred_old_status = old_status or store.permit_current_status.get(permit_id)
    candidate_status = normalized["normalized_status"]
    confidence = float(normalized["confidence"])
    manual_review_reason: str | None = None
    if candidate_status is None:
        manual_review_reason = "unmapped_status"
    elif confidence < AUTO_APPLY_CONFIDENCE_THRESHOLD:
        manual_review_reason = "low_confidence"
    elif inferred_old_status and not is_valid_transition(inferred_old_status, candidate_status):
        manual_review_reason = "invalid_transition"

    applied = manual_review_reason is None and candidate_status is not None
    review = None
    if manual_review_reason is not None:
        review = _build_manual_review(
            organization_id=organization_id,
            permit_id=permit_id,
            status_event_id=event["id"],
            from_status=inferred_old_status or candidate_status,
            to_status=candidate_status,
            rejection_reason=manual_review_reason,
            observed_at=observed_at,
        )
        store.transition_reviews.append(review)

    if applied and candidate_status:
        store.permit_current_status[permit_id] = candidate_status

    observed_event = None
    if candidate_status is not None:
        observed_event = build_status_observed_event(
            organization_id=organization_id,
            permit_id=permit_id,
            raw_status=raw_status,
            normalized_status=candidate_status,
            source=source,
            confidence=confidence,
            observed_at=observed_at,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
    changed_event = None
    if (
        applied
        and inferred_old_status
        and candidate_status
        and inferred_old_status != candidate_status
    ):
        changed_event = build_status_changed_event(
            organization_id=organization_id,
            permit_id=permit_id,
            old_status=inferred_old_status,
            new_status=candidate_status,
            source_event_id=event["id"],
            trace_id=trace_id,
            idempotency_key=f"{idempotency_key}:permit.status_changed:v1",
            occurred_at=observed_at,
        )
    return {
        "status_event": event,
        "provenance": provenance,
        "normalized": normalized,
        "applied": applied,
        "review": review,
        "observed_event": observed_event,
        "changed_event": changed_event,
    }


def record_status_observation_persisted(
    *,
    permit_id: str,
    source: str,
    raw_status: str,
    old_status: str | None,
    organization_id: str,
    connector: str,
    ahj_id: str,
    observed_at: datetime,
    parser_version: str,
    event_hash: str,
    trace_id: str,
    idempotency_key: str,
    rules: list[dict] | None,
    provenance_source_type: str = "api",
    provenance_source_ref: str | None = None,
    source_payload_hash: str | None = None,
    repository: Stage2Repository,
) -> dict:
    normalized = normalize_status(
        raw_status=raw_status,
        connector=connector,
        ahj_id=ahj_id,
        rules=rules,
    )
    created, event = repository.insert_status_event_with_provenance(
        event={
            "organization_id": organization_id,
            "permit_id": permit_id,
            "raw_status": raw_status,
            "normalized_status": normalized["normalized_status"],
            "source": source,
            "confidence": normalized["confidence"],
            "observed_at": _iso(observed_at),
            "parser_version": parser_version,
            "event_hash": event_hash,
        },
        provenance={
            "source_type": provenance_source_type,
            "source_ref": provenance_source_ref or f"{connector}:{source}",
            "source_payload_hash": source_payload_hash or event_hash,
            "parser_version": parser_version,
            "ingested_at": _iso(observed_at),
        },
    )
    provenance = repository.get_status_provenance(event["id"]) or {}
    candidate_status = normalized["normalized_status"]
    confidence = float(normalized["confidence"])
    projection = repository.get_status_projection(permit_id)
    inferred_old_status = old_status or (projection["current_status"] if projection else None)

    if not created:
        return {
            "status_event": event,
            "provenance": provenance,
            "normalized": normalized,
            "applied": False,
            "review": None,
            "observed_event": None,
            "changed_event": None,
        }

    manual_review_reason: str | None = None
    if candidate_status is None:
        manual_review_reason = "unmapped_status"
    elif confidence < AUTO_APPLY_CONFIDENCE_THRESHOLD:
        manual_review_reason = "low_confidence"
    elif inferred_old_status and not is_valid_transition(inferred_old_status, candidate_status):
        manual_review_reason = "invalid_transition"

    observed_event = None
    if candidate_status is not None:
        observed_event = build_status_observed_event(
            organization_id=organization_id,
            permit_id=permit_id,
            raw_status=raw_status,
            normalized_status=candidate_status,
            source=source,
            confidence=confidence,
            observed_at=observed_at,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        repository.insert_outbox_event(observed_event)

    applied = manual_review_reason is None and candidate_status is not None
    review = None
    changed_event = None
    if manual_review_reason is not None:
        if candidate_status is None:
            review = repository.insert_drift_alert(
                {
                    "organization_id": organization_id,
                    "permit_id": permit_id,
                    "connector": connector,
                    "ahj_id": ahj_id,
                    "drift_type": "timeline_gap",
                    "severity": "medium",
                    "status": "open",
                    "details_json": {
                        "reason": manual_review_reason,
                        "raw_status": raw_status,
                        "event_id": event["id"],
                    },
                    "detected_at": _iso(observed_at),
                }
            )
        else:
            review = repository.insert_transition_review(
                _build_manual_review(
                    organization_id=organization_id,
                    permit_id=permit_id,
                    status_event_id=event["id"],
                    from_status=inferred_old_status or candidate_status,
                    to_status=candidate_status,
                    rejection_reason=manual_review_reason,
                    observed_at=observed_at,
                )
            )

    if applied and candidate_status:
        repository.upsert_status_projection(
            {
                "permit_id": permit_id,
                "organization_id": organization_id,
                "current_status": candidate_status,
                "source_event_id": event["id"],
                "confidence": confidence,
                "updated_at": _iso(observed_at),
            }
        )

        if inferred_old_status and inferred_old_status != candidate_status:
            changed_event = build_status_changed_event(
                organization_id=organization_id,
                permit_id=permit_id,
                old_status=inferred_old_status,
                new_status=candidate_status,
                source_event_id=event["id"],
                trace_id=trace_id,
                idempotency_key=f"{idempotency_key}:permit.status_changed:v1",
                occurred_at=observed_at,
            )
            repository.insert_outbox_event(changed_event)

    return {
        "status_event": event,
        "provenance": provenance,
        "normalized": normalized,
        "applied": applied,
        "review": review,
        "observed_event": observed_event,
        "changed_event": changed_event,
    }
