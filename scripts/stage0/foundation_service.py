from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import hmac
import json
import uuid


ROLE_PRECEDENCE = {
    "subcontractor": 1,
    "reviewer": 2,
    "pm": 3,
    "admin": 4,
    "owner": 5,
}

ORG_ADMIN_ROLES = {"owner", "admin"}
PROJECT_WRITE_ROLES = {"owner", "admin", "pm"}
TASK_CREATE_ROLES = {"owner", "admin", "pm", "reviewer"}
TASK_UPDATE_ROLES = {"owner", "admin", "pm", "reviewer"}
DOCUMENT_UPLOAD_ROLES = {"owner", "admin", "pm", "reviewer", "subcontractor"}
NOTIFICATION_WRITE_ROLES = {"owner", "admin", "pm"}

TASK_STATUSES = {"todo", "in_progress", "blocked", "done"}
PERMIT_STATUSES = {
    "draft",
    "submitted",
    "in_review",
    "corrections_required",
    "approved",
    "issued",
    "expired",
}
DOCUMENT_OCR_STATUSES = {"uploaded", "scanning", "queued_for_ocr", "processing", "completed", "failed"}
ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}

PERMIT_TRANSITIONS = {
    "draft": {"submitted"},
    "submitted": {"in_review"},
    "in_review": {"corrections_required", "approved", "issued", "expired"},
    "corrections_required": {"submitted", "expired"},
    "approved": {"issued", "expired"},
    "issued": {"expired"},
    "expired": set(),
}


class Stage0RequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    user_id: str
    requester_role: str


@dataclass
class Stage0Store:
    organizations_by_id: dict[str, dict]
    organizations_by_slug: dict[str, str]
    workspaces_by_id: dict[str, dict]
    users_by_id: dict[str, dict]
    users_by_email: dict[str, str]
    memberships_by_id: dict[str, dict]
    memberships_by_org_user: dict[tuple[str, str], list[dict]]
    membership_org_level_index: set[tuple[str, str]]
    membership_workspace_level_index: set[tuple[str, str, str]]
    ahj_profiles_by_id: dict[str, dict]
    projects_by_id: dict[str, dict]
    projects_by_org_code: dict[tuple[str, str], str]
    permits_by_id: dict[str, dict]
    tasks_by_id: dict[str, dict]
    task_comments_by_id: dict[str, dict]
    documents_by_id: dict[str, dict]
    document_versions_by_id: dict[str, dict]
    document_version_by_doc_version: dict[tuple[str, int], str]
    document_tags_by_id: dict[str, dict]
    document_tag_index: set[tuple[str, str]]
    audit_events: list[dict]
    domain_events: list[dict]
    domain_event_by_org_idempotency: dict[tuple[str, str], dict]
    notification_jobs_by_id: dict[str, dict]
    notification_job_by_org_dedupe_channel: dict[tuple[str, str, str], str]
    request_dedup: dict[tuple[str, str], dict]
    signing_secret: bytes

    @classmethod
    def empty(cls, *, signing_secret: bytes | None = None) -> "Stage0Store":
        return cls(
            organizations_by_id={},
            organizations_by_slug={},
            workspaces_by_id={},
            users_by_id={},
            users_by_email={},
            memberships_by_id={},
            memberships_by_org_user={},
            membership_org_level_index=set(),
            membership_workspace_level_index=set(),
            ahj_profiles_by_id={},
            projects_by_id={},
            projects_by_org_code={},
            permits_by_id={},
            tasks_by_id={},
            task_comments_by_id={},
            documents_by_id={},
            document_versions_by_id={},
            document_version_by_doc_version={},
            document_tags_by_id={},
            document_tag_index=set(),
            audit_events=[],
            domain_events=[],
            domain_event_by_org_idempotency={},
            notification_jobs_by_id={},
            notification_job_by_org_dedupe_channel={},
            request_dedup={},
            signing_secret=signing_secret or b"stage0-dev-secret",
        )


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _trace_id(trace_id: str | None) -> str:
    if trace_id and trace_id.strip():
        return trace_id.strip()
    return str(uuid.uuid4())


def _request_id(request_id: str | None) -> str:
    if request_id and request_id.strip():
        return request_id.strip()
    return f"req_{uuid.uuid4()}"


def _stable_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _event_signature(event: dict, *, signing_secret: bytes) -> str:
    message = json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(signing_secret, message, hashlib.sha256).hexdigest()


def _record_request(
    *,
    store: Stage0Store,
    scope: str,
    key: str,
    request_payload: dict,
    status: int,
    response_payload: dict,
) -> None:
    store.request_dedup[(scope, key)] = {
        "request_hash": _stable_hash(request_payload),
        "status": status,
        "response": response_payload,
    }


def _check_request_replay(
    *,
    store: Stage0Store,
    scope: str,
    key: str,
    request_payload: dict,
) -> tuple[bool, int | None, dict | None]:
    existing = store.request_dedup.get((scope, key))
    if not existing:
        return False, None, None
    incoming = _stable_hash(request_payload)
    if incoming != existing["request_hash"]:
        raise Stage0RequestError(409, "conflict", "idempotency key reused with different request payload")
    return True, int(existing["status"]), dict(existing["response"])


def _require_role(auth: AuthContext, allowed: set[str], *, message: str) -> None:
    if auth.requester_role not in allowed:
        raise Stage0RequestError(403, "forbidden", message)


def _org_memberships_for_user(store: Stage0Store, *, organization_id: str, user_id: str) -> list[dict]:
    return list(store.memberships_by_org_user.get((organization_id, user_id), []))


def _effective_project_roles(
    store: Stage0Store,
    *,
    organization_id: str,
    workspace_id: str,
    user_id: str,
) -> set[str]:
    roles: set[str] = set()
    for m in _org_memberships_for_user(store, organization_id=organization_id, user_id=user_id):
        if m.get("workspace_id") is None or m.get("workspace_id") == workspace_id:
            roles.add(str(m["role"]))
    return roles


def _require_org_context(auth: AuthContext, *, organization_id: str) -> None:
    if auth.organization_id != organization_id:
        raise Stage0RequestError(403, "forbidden", "organization mismatch")


def _require_project_access(store: Stage0Store, *, auth: AuthContext, project: dict) -> None:
    roles = _effective_project_roles(
        store,
        organization_id=str(project["organization_id"]),
        workspace_id=str(project["workspace_id"]),
        user_id=auth.user_id,
    )
    if not roles:
        raise Stage0RequestError(403, "forbidden", "caller is not a member of project workspace")


def _get_project_for_org(store: Stage0Store, *, organization_id: str, project_id: str) -> dict:
    project = store.projects_by_id.get(project_id)
    if not project or project["organization_id"] != organization_id:
        raise Stage0RequestError(404, "not_found", "project not found")
    return project


def _get_task_for_org(store: Stage0Store, *, organization_id: str, task_id: str) -> dict:
    task = store.tasks_by_id.get(task_id)
    if not task or task["organization_id"] != organization_id:
        raise Stage0RequestError(404, "not_found", "task not found")
    return task


def _get_permit_for_org(store: Stage0Store, *, organization_id: str, permit_id: str) -> dict:
    permit = store.permits_by_id.get(permit_id)
    if not permit or permit["organization_id"] != organization_id:
        raise Stage0RequestError(404, "not_found", "permit not found")
    return permit


def _append_audit_event(
    *,
    store: Stage0Store,
    organization_id: str,
    project_id: str | None,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    request_id: str,
    trace_id: str,
    payload: dict,
    now: datetime,
) -> dict:
    prev_hash = None
    for ev in reversed(store.audit_events):
        if ev["organization_id"] == organization_id:
            prev_hash = ev["event_hash"]
            break
    base = {
        "organization_id": organization_id,
        "project_id": project_id,
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "occurred_at": _iso(now),
        "request_id": request_id,
        "trace_id": trace_id,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    event_hash = hashlib.sha256(json.dumps(base, sort_keys=True).encode("utf-8")).hexdigest()
    event = {
        "id": str(uuid.uuid4()),
        **base,
        "event_hash": event_hash,
        "immutable": True,
    }
    store.audit_events.append(event)
    return event


def verify_audit_chain(*, organization_id: str, store: Stage0Store) -> tuple[bool, str | None]:
    """
    Verifies immutable audit continuity for a single organization.
    Returns (is_valid, failing_event_id).
    """
    prior_hash = None
    for event in [ev for ev in store.audit_events if ev.get("organization_id") == organization_id]:
        base = {
            "organization_id": event.get("organization_id"),
            "project_id": event.get("project_id"),
            "actor_user_id": event.get("actor_user_id"),
            "action": event.get("action"),
            "entity_type": event.get("entity_type"),
            "entity_id": event.get("entity_id"),
            "occurred_at": event.get("occurred_at"),
            "request_id": event.get("request_id"),
            "trace_id": event.get("trace_id"),
            "payload": event.get("payload"),
            "prev_hash": prior_hash,
        }
        expected = hashlib.sha256(json.dumps(base, sort_keys=True).encode("utf-8")).hexdigest()
        if event.get("event_hash") != expected:
            return False, str(event.get("id"))
        if event.get("prev_hash") != prior_hash:
            return False, str(event.get("id"))
        prior_hash = expected
    return True, None


def _emit_domain_event(
    *,
    store: Stage0Store,
    organization_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    produced_by: str,
    now: datetime,
) -> dict:
    dedupe_key = (organization_id, idempotency_key)
    existing = store.domain_event_by_org_idempotency.get(dedupe_key)
    if existing:
        return existing

    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "occurred_at": _iso(now),
        "produced_by": produced_by,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }
    signature = _event_signature(envelope, signing_secret=store.signing_secret)
    event = {
        **envelope,
        "signature": signature,
        "status": "pending",
        "publish_attempts": 0,
        "published_at": None,
        "created_at": _iso(now),
    }
    store.domain_events.append(event)
    store.domain_event_by_org_idempotency[dedupe_key] = event
    return event


def _enqueue_notification_job(
    *,
    store: Stage0Store,
    organization_id: str,
    user_id: str,
    channel: str,
    template_key: str,
    dedupe_key: str,
    payload: dict,
    now: datetime,
) -> dict:
    dedupe_idx = (organization_id, dedupe_key, channel)
    existing_id = store.notification_job_by_org_dedupe_channel.get(dedupe_idx)
    if existing_id:
        return store.notification_jobs_by_id[existing_id]

    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "organization_id": organization_id,
        "user_id": user_id,
        "channel": channel,
        "template_key": template_key,
        "dedupe_key": dedupe_key,
        "status": "pending",
        "payload": payload,
        "attempt_count": 0,
        "next_attempt_at": _iso(now),
        "provider_message_id": None,
        "last_error": None,
        "created_at": _iso(now),
        "sent_at": None,
    }
    store.notification_jobs_by_id[job_id] = job
    store.notification_job_by_org_dedupe_channel[dedupe_idx] = job_id
    return job


def _create_user_if_missing(store: Stage0Store, *, email: str, full_name: str, now: datetime) -> dict:
    normalized = email.strip().lower()
    existing_id = store.users_by_email.get(normalized)
    if existing_id:
        return store.users_by_id[existing_id]
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": normalized,
        "full_name": full_name.strip(),
        "status": "active",
        "created_at": _iso(now),
    }
    store.users_by_id[user_id] = user
    store.users_by_email[normalized] = user_id
    return user


def _add_membership(
    *,
    store: Stage0Store,
    organization_id: str,
    user_id: str,
    role: str,
    workspace_id: str | None,
    invited_by: str | None,
    now: datetime,
) -> dict:
    if role not in ROLE_PRECEDENCE:
        raise Stage0RequestError(422, "validation_failed", "invalid role")

    if workspace_id is None:
        idx = (organization_id, user_id)
        if idx in store.membership_org_level_index:
            raise Stage0RequestError(409, "conflict", "org-level membership already exists")
    else:
        ws = store.workspaces_by_id.get(workspace_id)
        if not ws or ws["organization_id"] != organization_id:
            raise Stage0RequestError(404, "not_found", "workspace not found in organization")
        idx = (organization_id, workspace_id, user_id)
        if idx in store.membership_workspace_level_index:
            raise Stage0RequestError(409, "conflict", "workspace-level membership already exists")

    membership_id = str(uuid.uuid4())
    membership = {
        "id": membership_id,
        "organization_id": organization_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "invited_by": invited_by,
        "created_at": _iso(now),
    }
    store.memberships_by_id[membership_id] = membership
    store.memberships_by_org_user.setdefault((organization_id, user_id), []).append(membership)
    if workspace_id is None:
        store.membership_org_level_index.add((organization_id, user_id))
    else:
        store.membership_workspace_level_index.add((organization_id, workspace_id, user_id))
    return membership


def post_orgs(
    *,
    request_body: dict,
    idempotency_key: str,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    if not idempotency_key.strip():
        raise Stage0RequestError(400, "bad_request", "Idempotency-Key is required")

    name = str(request_body.get("name") or "").strip()
    slug = str(request_body.get("slug") or "").strip().lower()
    owner = request_body.get("owner_user") or {}
    owner_email = str(owner.get("email") or "").strip().lower()
    owner_name = str(owner.get("full_name") or "").strip()
    if not name or not slug or not owner_email or not owner_name:
        raise Stage0RequestError(422, "validation_failed", "name, slug, and owner_user are required")

    scope = f"POST:/orgs:{slug}"
    replay, replay_status, replay_payload = _check_request_replay(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
    )
    if replay:
        replay_payload["idempotency_replayed"] = True
        return 200, replay_payload

    if slug in store.organizations_by_slug:
        raise Stage0RequestError(409, "conflict", "organization slug already exists")

    owner_user = _create_user_if_missing(store, email=owner_email, full_name=owner_name, now=ts)
    organization_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())

    organization = {
        "id": organization_id,
        "name": name,
        "slug": slug,
        "created_by": owner_user["id"],
        "created_at": _iso(ts),
    }
    store.organizations_by_id[organization_id] = organization
    store.organizations_by_slug[slug] = organization_id

    workspace = {
        "id": workspace_id,
        "organization_id": organization_id,
        "name": "Default",
        "is_default": True,
        "created_at": _iso(ts),
    }
    store.workspaces_by_id[workspace_id] = workspace

    owner_membership = _add_membership(
        store=store,
        organization_id=organization_id,
        user_id=owner_user["id"],
        role="owner",
        workspace_id=None,
        invited_by=owner_user["id"],
        now=ts,
    )

    _append_audit_event(
        store=store,
        organization_id=organization_id,
        project_id=None,
        actor_user_id=owner_user["id"],
        action="org.created",
        entity_type="organization",
        entity_id=organization_id,
        request_id=rid,
        trace_id=tid,
        payload={"slug": slug},
        now=ts,
    )

    response = {
        "organization": {"id": organization_id, "name": name, "slug": slug},
        "default_workspace": {"id": workspace_id, "name": "Default"},
        "owner_membership": {"id": owner_membership["id"], "role": "owner"},
        "idempotency_replayed": False,
    }
    _record_request(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
        status=201,
        response_payload=response,
    )
    return 201, response


def post_org_user_invite(
    *,
    org_id: str,
    request_body: dict,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_org_context(auth_context, organization_id=org_id)
    _require_role(auth_context, ORG_ADMIN_ROLES, message="role cannot invite users")

    if org_id not in store.organizations_by_id:
        raise Stage0RequestError(404, "not_found", "organization not found")

    email = str(request_body.get("email") or "").strip().lower()
    full_name = str(request_body.get("full_name") or "").strip()
    role = str(request_body.get("role") or "").strip()
    workspace_id_raw = request_body.get("workspace_id")
    workspace_id = str(workspace_id_raw).strip() if workspace_id_raw else None
    if not email or not full_name or not role:
        raise Stage0RequestError(422, "validation_failed", "email, full_name, role are required")

    user = _create_user_if_missing(store, email=email, full_name=full_name, now=ts)
    membership = _add_membership(
        store=store,
        organization_id=org_id,
        user_id=user["id"],
        role=role,
        workspace_id=workspace_id,
        invited_by=auth_context.user_id,
        now=ts,
    )

    _append_audit_event(
        store=store,
        organization_id=org_id,
        project_id=None,
        actor_user_id=auth_context.user_id,
        action="membership.created",
        entity_type="membership",
        entity_id=membership["id"],
        request_id=rid,
        trace_id=tid,
        payload={"user_id": user["id"], "role": role, "workspace_id": workspace_id},
        now=ts,
    )

    return 201, {"membership": membership}


def post_projects(
    *,
    request_body: dict,
    idempotency_key: str,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_role(auth_context, PROJECT_WRITE_ROLES, message="role cannot create projects")

    org_id = str(request_body.get("organization_id") or "").strip()
    workspace_id = str(request_body.get("workspace_id") or "").strip()
    name = str(request_body.get("name") or "").strip()
    project_code = str(request_body.get("project_code") or "").strip()
    if not org_id or not workspace_id or not name:
        raise Stage0RequestError(422, "validation_failed", "organization_id, workspace_id, name are required")
    if not idempotency_key.strip():
        raise Stage0RequestError(400, "bad_request", "Idempotency-Key is required")
    _require_org_context(auth_context, organization_id=org_id)

    ws = store.workspaces_by_id.get(workspace_id)
    if not ws or ws["organization_id"] != org_id:
        raise Stage0RequestError(404, "not_found", "workspace not found in organization")

    scope = f"POST:/projects:{org_id}"
    replay, _, replay_payload = _check_request_replay(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
    )
    if replay:
        return 200, replay_payload

    if project_code and (org_id, project_code) in store.projects_by_org_code:
        raise Stage0RequestError(409, "conflict", "project code already exists in organization")

    ahj_payload = request_body.get("ahj_profile")
    ahj_profile = None
    if isinstance(ahj_payload, dict):
        ahj_name = str(ahj_payload.get("name") or "").strip()
        jurisdiction_type = str(ahj_payload.get("jurisdiction_type") or "").strip()
        if not ahj_name or not jurisdiction_type:
            raise Stage0RequestError(422, "validation_failed", "ahj_profile.name and jurisdiction_type are required")
        ahj_id = str(uuid.uuid4())
        ahj_profile = {
            "id": ahj_id,
            "organization_id": org_id,
            "name": ahj_name,
            "jurisdiction_type": jurisdiction_type,
            "region": ahj_payload.get("region"),
            "metadata": {},
            "created_at": _iso(ts),
        }
        store.ahj_profiles_by_id[ahj_id] = ahj_profile

    project_id = str(uuid.uuid4())
    project = {
        "id": project_id,
        "organization_id": org_id,
        "workspace_id": workspace_id,
        "ahj_profile_id": ahj_profile["id"] if ahj_profile else None,
        "name": name,
        "project_code": project_code or None,
        "address": request_body.get("address") or {},
        "metadata": request_body.get("metadata") or {},
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.projects_by_id[project_id] = project
    if project_code:
        store.projects_by_org_code[(org_id, project_code)] = project_id

    _append_audit_event(
        store=store,
        organization_id=org_id,
        project_id=project_id,
        actor_user_id=auth_context.user_id,
        action="project.created",
        entity_type="project",
        entity_id=project_id,
        request_id=rid,
        trace_id=tid,
        payload={"project_code": project_code or None},
        now=ts,
    )

    response = {"project": project, "ahj_profile": ahj_profile}
    _record_request(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
        status=201,
        response_payload=response,
    )
    return 201, response


def post_project_permits(
    *,
    project_id: str,
    request_body: dict,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_role(auth_context, PROJECT_WRITE_ROLES, message="role cannot create permit")
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=project_id)
    _require_project_access(store, auth=auth_context, project=project)

    permit_type = str(request_body.get("permit_type") or "").strip()
    if not permit_type:
        raise Stage0RequestError(422, "validation_failed", "permit_type is required")
    permit_id = str(uuid.uuid4())
    permit = {
        "id": permit_id,
        "organization_id": auth_context.organization_id,
        "project_id": project_id,
        "permit_type": permit_type,
        "status": "draft",
        "submitted_at": None,
        "issued_at": None,
        "expired_at": None,
        "metadata": request_body.get("metadata") or {},
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
    }
    store.permits_by_id[permit_id] = permit

    _append_audit_event(
        store=store,
        organization_id=auth_context.organization_id,
        project_id=project_id,
        actor_user_id=auth_context.user_id,
        action="permit.created",
        entity_type="permit",
        entity_id=permit_id,
        request_id=rid,
        trace_id=tid,
        payload={"status": "draft", "permit_type": permit_type},
        now=ts,
    )
    return 201, {"permit": permit}


def patch_permits(
    *,
    permit_id: str,
    request_body: dict,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_role(auth_context, PROJECT_WRITE_ROLES, message="role cannot update permit")
    permit = _get_permit_for_org(store, organization_id=auth_context.organization_id, permit_id=permit_id)
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=permit["project_id"])
    _require_project_access(store, auth=auth_context, project=project)

    new_status = str(request_body.get("status") or "").strip()
    source = str(request_body.get("source") or "user_action")
    if new_status not in PERMIT_STATUSES:
        raise Stage0RequestError(422, "validation_failed", "invalid permit status")

    old_status = permit["status"]
    if old_status != new_status and new_status not in PERMIT_TRANSITIONS[old_status]:
        raise Stage0RequestError(422, "validation_failed", "invalid permit status transition")

    permit["status"] = new_status
    if new_status == "submitted" and permit["submitted_at"] is None:
        permit["submitted_at"] = _iso(ts)
    if new_status == "issued" and permit["issued_at"] is None:
        permit["issued_at"] = _iso(ts)
    if new_status == "expired" and permit["expired_at"] is None:
        permit["expired_at"] = _iso(ts)
    permit["updated_at"] = _iso(ts)

    _append_audit_event(
        store=store,
        organization_id=auth_context.organization_id,
        project_id=permit["project_id"],
        actor_user_id=auth_context.user_id,
        action="permit.status_changed",
        entity_type="permit",
        entity_id=permit_id,
        request_id=rid,
        trace_id=tid,
        payload={"old_status": old_status, "new_status": new_status, "source": source},
        now=ts,
    )
    _emit_domain_event(
        store=store,
        organization_id=auth_context.organization_id,
        aggregate_type="permit",
        aggregate_id=permit_id,
        event_type="permit.status_changed",
        idempotency_key=f"{rid}:permit.status_changed:{permit_id}:{old_status}->{new_status}",
        trace_id=tid,
        payload={
            "permit_id": permit_id,
            "project_id": permit["project_id"],
            "old_status": old_status,
            "new_status": new_status,
            "source": source,
            "changed_at": _iso(ts),
            "changed_by": auth_context.user_id,
        },
        produced_by="permit-service",
        now=ts,
    )
    return 200, {"permit": permit}


def post_project_documents(
    *,
    project_id: str,
    request_body: dict,
    idempotency_key: str,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_role(auth_context, DOCUMENT_UPLOAD_ROLES, message="role cannot upload documents")
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=project_id)
    _require_project_access(store, auth=auth_context, project=project)
    if not idempotency_key.strip():
        raise Stage0RequestError(400, "bad_request", "Idempotency-Key is required")

    scope = f"POST:/projects/{project_id}/documents:{auth_context.organization_id}"
    replay, _, replay_payload = _check_request_replay(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
    )
    if replay:
        return 200, replay_payload

    title = str(request_body.get("title") or "").strip()
    category = request_body.get("category")
    file_name = str(request_body.get("file_name") or "").strip()
    mime_type = str(request_body.get("mime_type") or "").strip().lower()
    file_size_bytes = int(request_body.get("file_size_bytes") or 0)
    checksum_sha256 = str(request_body.get("checksum_sha256") or "").strip()
    storage_upload = request_body.get("storage_upload") or {}
    bucket = str(storage_upload.get("bucket") or "").strip()
    key = str(storage_upload.get("key") or "").strip()
    if not title or not file_name or not mime_type or not bucket or not key or not checksum_sha256:
        raise Stage0RequestError(422, "validation_failed", "missing required document upload fields")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise Stage0RequestError(415, "unsupported_media_type", "mime type is not allowed")
    if file_size_bytes <= 0:
        raise Stage0RequestError(422, "validation_failed", "file_size_bytes must be positive")

    existing_doc_id = request_body.get("document_id")
    if existing_doc_id:
        existing_doc_id = str(existing_doc_id)
        document = store.documents_by_id.get(existing_doc_id)
        if not document or document["organization_id"] != auth_context.organization_id:
            raise Stage0RequestError(404, "not_found", "document not found")
        if document["project_id"] != project_id:
            raise Stage0RequestError(422, "validation_failed", "document does not belong to project")
        version_no = int(document["latest_version_no"]) + 1
    else:
        doc_id = str(uuid.uuid4())
        document = {
            "id": doc_id,
            "organization_id": auth_context.organization_id,
            "project_id": project_id,
            "latest_version_no": 0,
            "title": title,
            "category": category,
            "created_by": auth_context.user_id,
            "created_at": _iso(ts),
            "updated_at": _iso(ts),
        }
        store.documents_by_id[doc_id] = document
        version_no = 1

    version_id = str(uuid.uuid4())
    document["latest_version_no"] = version_no
    document["updated_at"] = _iso(ts)
    version = {
        "id": version_id,
        "organization_id": auth_context.organization_id,
        "document_id": document["id"],
        "version_no": version_no,
        "storage_key": key,
        "storage_bucket": bucket,
        "file_name": file_name,
        "file_size_bytes": file_size_bytes,
        "mime_type": mime_type,
        "checksum_sha256": checksum_sha256,
        "uploaded_by": auth_context.user_id,
        "uploaded_at": _iso(ts),
        "virus_scan_status": "pending",
        "virus_scan_completed_at": None,
        "ocr_status": "uploaded",
        "ocr_page_count": None,
        "ocr_error_code": None,
        "ocr_completed_at": None,
    }
    store.document_versions_by_id[version_id] = version
    store.document_version_by_doc_version[(document["id"], version_no)] = version_id

    _append_audit_event(
        store=store,
        organization_id=auth_context.organization_id,
        project_id=project_id,
        actor_user_id=auth_context.user_id,
        action="document.uploaded",
        entity_type="document_version",
        entity_id=version_id,
        request_id=rid,
        trace_id=tid,
        payload={"document_id": document["id"], "version": version_no, "mime_type": mime_type},
        now=ts,
    )
    _emit_domain_event(
        store=store,
        organization_id=auth_context.organization_id,
        aggregate_type="document",
        aggregate_id=document["id"],
        event_type="document.uploaded",
        idempotency_key=f"{rid}:document.uploaded:{document['id']}:v{version_no}",
        trace_id=tid,
        payload={
            "document_id": document["id"],
            "project_id": project_id,
            "uploader_id": auth_context.user_id,
            "version": version_no,
            "uploaded_at": _iso(ts),
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
        },
        produced_by="document-service",
        now=ts,
    )

    response = {"document": document, "version": version, "upload_status": "accepted"}
    _record_request(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
        status=201,
        response_payload=response,
    )
    return 201, response


def mark_document_ocr_completed(
    *,
    document_id: str,
    version: int,
    ocr_status: str,
    page_count: int | None,
    error_code: str | None,
    organization_id: str,
    store: Stage0Store,
    now: datetime | None = None,
    trace_id: str | None = None,
) -> dict:
    ts = _now(now)
    tid = _trace_id(trace_id)
    if ocr_status not in {"completed", "failed"}:
        raise Stage0RequestError(422, "validation_failed", "ocr_status must be completed or failed")
    version_id = store.document_version_by_doc_version.get((document_id, int(version)))
    if not version_id:
        raise Stage0RequestError(404, "not_found", "document version not found")
    row = store.document_versions_by_id[version_id]
    if row["organization_id"] != organization_id:
        raise Stage0RequestError(403, "forbidden", "document version belongs to another organization")
    current_status = str(row.get("ocr_status") or "uploaded")
    if current_status in {"completed", "failed"} and current_status != ocr_status:
        raise Stage0RequestError(
            409,
            "conflict",
            "ocr_status is terminal for this document version; upload a new version for reprocessing",
        )
    row["ocr_status"] = ocr_status
    row["ocr_page_count"] = page_count
    row["ocr_error_code"] = error_code
    row["ocr_completed_at"] = _iso(ts)

    _emit_domain_event(
        store=store,
        organization_id=organization_id,
        aggregate_type="document",
        aggregate_id=document_id,
        event_type="document.ocr_completed",
        idempotency_key=f"{document_id}:v{version}:document.ocr_completed",
        trace_id=tid,
        payload={
            "document_id": document_id,
            "version": int(version),
            "ocr_status": ocr_status,
            "page_count": page_count,
            "completed_at": _iso(ts),
            "error_code": error_code,
        },
        produced_by="document-processing-worker",
        now=ts,
    )
    return row


def post_project_tasks(
    *,
    project_id: str,
    request_body: dict,
    idempotency_key: str,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    _require_role(auth_context, TASK_CREATE_ROLES, message="role cannot create tasks")
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=project_id)
    _require_project_access(store, auth=auth_context, project=project)
    if not idempotency_key.strip():
        raise Stage0RequestError(400, "bad_request", "Idempotency-Key is required")

    scope = f"POST:/projects/{project_id}/tasks:{auth_context.organization_id}"
    replay, _, replay_payload = _check_request_replay(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
    )
    if replay:
        return 200, replay_payload

    title = str(request_body.get("title") or "").strip()
    if not title:
        raise Stage0RequestError(422, "validation_failed", "title is required")
    due_date_raw = request_body.get("due_date")
    due_value = None
    if due_date_raw:
        try:
            due_value = date.fromisoformat(str(due_date_raw)).isoformat()
        except ValueError as exc:
            raise Stage0RequestError(422, "validation_failed", "due_date must be YYYY-MM-DD") from exc

    priority = int(request_body.get("priority") or 3)
    if priority < 1 or priority > 5:
        raise Stage0RequestError(422, "validation_failed", "priority must be between 1 and 5")

    permit_id = request_body.get("permit_id")
    if permit_id:
        permit = _get_permit_for_org(store, organization_id=auth_context.organization_id, permit_id=str(permit_id))
        if permit["project_id"] != project_id:
            raise Stage0RequestError(422, "validation_failed", "permit does not belong to project")

    assignee_user_id = request_body.get("assignee_user_id")
    if assignee_user_id:
        assignee_user_id = str(assignee_user_id)
        if assignee_user_id not in store.users_by_id:
            raise Stage0RequestError(404, "not_found", "assignee user not found")
        assignee_roles = _effective_project_roles(
            store,
            organization_id=auth_context.organization_id,
            workspace_id=project["workspace_id"],
            user_id=assignee_user_id,
        )
        if not assignee_roles:
            raise Stage0RequestError(422, "validation_failed", "assignee is not a member of project workspace")

    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "organization_id": auth_context.organization_id,
        "project_id": project_id,
        "permit_id": str(permit_id) if permit_id else None,
        "title": title,
        "description": request_body.get("description"),
        "discipline": request_body.get("discipline"),
        "status": "todo",
        "assignee_user_id": assignee_user_id,
        "due_date": due_value,
        "priority": priority,
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
        "version": 1,
    }
    store.tasks_by_id[task_id] = task

    _append_audit_event(
        store=store,
        organization_id=auth_context.organization_id,
        project_id=project_id,
        actor_user_id=auth_context.user_id,
        action="task.created",
        entity_type="task",
        entity_id=task_id,
        request_id=rid,
        trace_id=tid,
        payload={"discipline": task["discipline"], "assignee_user_id": assignee_user_id},
        now=ts,
    )
    _emit_domain_event(
        store=store,
        organization_id=auth_context.organization_id,
        aggregate_type="task",
        aggregate_id=task_id,
        event_type="task.created",
        idempotency_key=f"{rid}:task.created:{task_id}",
        trace_id=tid,
        payload={
            "task_id": task_id,
            "project_id": project_id,
            "permit_id": task["permit_id"],
            "discipline": task["discipline"],
            "created_by": auth_context.user_id,
            "assignee_user_id": assignee_user_id,
            "due_date": due_value,
        },
        produced_by="task-service",
        now=ts,
    )

    if assignee_user_id:
        _emit_domain_event(
            store=store,
            organization_id=auth_context.organization_id,
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task.assigned",
            idempotency_key=f"{rid}:task.assigned:{task_id}:{assignee_user_id}",
            trace_id=tid,
            payload={
                "task_id": task_id,
                "assignee_id": assignee_user_id,
                "assigned_by": auth_context.user_id,
                "assigned_at": _iso(ts),
            },
            produced_by="task-service",
            now=ts,
        )
        _enqueue_notification_job(
            store=store,
            organization_id=auth_context.organization_id,
            user_id=assignee_user_id,
            channel="in_app",
            template_key="task_assigned",
            dedupe_key=f"task:{task_id}:assigned",
            payload={"task_id": task_id, "project_id": project_id},
            now=ts,
        )
        _enqueue_notification_job(
            store=store,
            organization_id=auth_context.organization_id,
            user_id=assignee_user_id,
            channel="email",
            template_key="task_assigned",
            dedupe_key=f"task:{task_id}:assigned",
            payload={"task_id": task_id, "project_id": project_id},
            now=ts,
        )

    response = {"task": task}
    _record_request(
        store=store,
        scope=scope,
        key=idempotency_key,
        request_payload=request_body,
        status=201,
        response_payload=response,
    )
    return 201, response


def patch_tasks(
    *,
    task_id: str,
    request_body: dict,
    if_match_version: int,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> tuple[int, dict]:
    ts = _now(now)
    rid = _request_id(request_id)
    tid = _trace_id(trace_id)
    task = _get_task_for_org(store, organization_id=auth_context.organization_id, task_id=task_id)
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=task["project_id"])
    _require_project_access(store, auth=auth_context, project=project)

    allowed = auth_context.requester_role in TASK_UPDATE_ROLES
    if not allowed and auth_context.requester_role == "subcontractor":
        allowed = task["assignee_user_id"] == auth_context.user_id
    if not allowed:
        raise Stage0RequestError(403, "forbidden", "role cannot update task")

    if int(if_match_version) != int(task["version"]):
        raise Stage0RequestError(412, "precondition_failed", "task version mismatch")

    if auth_context.requester_role == "subcontractor":
        disallowed_fields = {"assignee_user_id", "due_date", "priority", "discipline", "title", "description"}
        for field in disallowed_fields:
            if field in request_body:
                raise Stage0RequestError(403, "forbidden", "subcontractor can only update task status")

    old_assignee = task["assignee_user_id"]
    old_status = task["status"]
    status_val = request_body.get("status")
    if status_val is not None:
        status_str = str(status_val)
        if status_str not in TASK_STATUSES:
            raise Stage0RequestError(422, "validation_failed", "invalid task status")
        if old_status == "done" and status_str != "done":
            raise Stage0RequestError(422, "validation_failed", "done tasks cannot be reopened in patch endpoint")
        task["status"] = status_str

    if "assignee_user_id" in request_body:
        new_assignee = request_body.get("assignee_user_id")
        if new_assignee is not None:
            new_assignee = str(new_assignee)
            if new_assignee not in store.users_by_id:
                raise Stage0RequestError(404, "not_found", "assignee user not found")
            if not _effective_project_roles(
                store,
                organization_id=auth_context.organization_id,
                workspace_id=project["workspace_id"],
                user_id=new_assignee,
            ):
                raise Stage0RequestError(422, "validation_failed", "assignee is not a member of project workspace")
        task["assignee_user_id"] = new_assignee

    if "due_date" in request_body:
        due_raw = request_body.get("due_date")
        if due_raw is None:
            task["due_date"] = None
        else:
            try:
                task["due_date"] = date.fromisoformat(str(due_raw)).isoformat()
            except ValueError as exc:
                raise Stage0RequestError(422, "validation_failed", "due_date must be YYYY-MM-DD") from exc

    if "priority" in request_body:
        priority = int(request_body["priority"])
        if priority < 1 or priority > 5:
            raise Stage0RequestError(422, "validation_failed", "priority must be between 1 and 5")
        task["priority"] = priority

    for k in ("discipline", "title", "description"):
        if k in request_body:
            task[k] = request_body[k]

    task["version"] = int(task["version"]) + 1
    task["updated_at"] = _iso(ts)

    _append_audit_event(
        store=store,
        organization_id=auth_context.organization_id,
        project_id=task["project_id"],
        actor_user_id=auth_context.user_id,
        action="task.updated",
        entity_type="task",
        entity_id=task_id,
        request_id=rid,
        trace_id=tid,
        payload={"old_status": old_status, "new_status": task["status"], "old_assignee": old_assignee, "new_assignee": task["assignee_user_id"]},
        now=ts,
    )

    if old_assignee != task["assignee_user_id"] and task["assignee_user_id"]:
        _emit_domain_event(
            store=store,
            organization_id=auth_context.organization_id,
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task.assigned",
            idempotency_key=f"{rid}:task.assigned:{task_id}:{task['assignee_user_id']}",
            trace_id=tid,
            payload={
                "task_id": task_id,
                "assignee_id": task["assignee_user_id"],
                "assigned_by": auth_context.user_id,
                "assigned_at": _iso(ts),
            },
            produced_by="task-service",
            now=ts,
        )
        _enqueue_notification_job(
            store=store,
            organization_id=auth_context.organization_id,
            user_id=task["assignee_user_id"],
            channel="in_app",
            template_key="task_assigned",
            dedupe_key=f"task:{task_id}:assigned:{task['version']}",
            payload={"task_id": task_id, "project_id": task["project_id"]},
            now=ts,
        )
        _enqueue_notification_job(
            store=store,
            organization_id=auth_context.organization_id,
            user_id=task["assignee_user_id"],
            channel="email",
            template_key="task_assigned",
            dedupe_key=f"task:{task_id}:assigned:{task['version']}",
            payload={"task_id": task_id, "project_id": task["project_id"]},
            now=ts,
        )

    return 200, {"task": task}


def get_project_timeline(
    *,
    project_id: str,
    auth_context: AuthContext,
    store: Stage0Store,
    query_params: dict | None = None,
) -> tuple[int, dict]:
    project = _get_project_for_org(store, organization_id=auth_context.organization_id, project_id=project_id)
    _require_project_access(store, auth=auth_context, project=project)

    qp = query_params or {}
    limit_raw = qp.get("limit", 50)
    try:
        limit = int(limit_raw)
    except ValueError as exc:
        raise Stage0RequestError(422, "validation_failed", "limit must be an integer") from exc
    if limit < 1 or limit > 200:
        raise Stage0RequestError(422, "validation_failed", "limit must be between 1 and 200")

    cursor = str(qp.get("cursor") or "").strip()
    event_types_raw = qp.get("event_types")
    event_types = None
    if event_types_raw:
        event_types = {part.strip() for part in str(event_types_raw).split(",") if part.strip()}

    from_ts = None
    to_ts = None
    if qp.get("from"):
        from_ts = datetime.fromisoformat(str(qp["from"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    if qp.get("to"):
        to_ts = datetime.fromisoformat(str(qp["to"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    if from_ts and to_ts and from_ts > to_ts:
        raise Stage0RequestError(422, "validation_failed", "from must be <= to")

    rows = [
        row
        for row in store.audit_events
        if row["organization_id"] == auth_context.organization_id and row["project_id"] == project_id
    ]
    rows.sort(key=lambda row: (row["occurred_at"], row["id"]), reverse=True)

    if event_types:
        rows = [row for row in rows if row["action"] in event_types]
    if from_ts:
        rows = [row for row in rows if datetime.fromisoformat(row["occurred_at"]) >= from_ts]
    if to_ts:
        rows = [row for row in rows if datetime.fromisoformat(row["occurred_at"]) <= to_ts]

    if cursor:
        try:
            cursor_ts_raw, cursor_id = cursor.split("|", 1)
            cursor_ts = datetime.fromisoformat(cursor_ts_raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as exc:
            raise Stage0RequestError(422, "validation_failed", "invalid cursor format") from exc
        rows = [
            row
            for row in rows
            if (datetime.fromisoformat(row["occurred_at"]).astimezone(timezone.utc), row["id"]) < (cursor_ts, cursor_id)
        ]

    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        tail = items[-1]
        next_cursor = f"{tail['occurred_at']}|{tail['id']}"

    payload = {
        "items": [
            {
                "id": row["id"],
                "occurred_at": row["occurred_at"],
                "action": row["action"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "actor_user_id": row["actor_user_id"],
                "payload": row["payload"],
            }
            for row in items
        ],
        "next_cursor": next_cursor,
    }
    return 200, payload
