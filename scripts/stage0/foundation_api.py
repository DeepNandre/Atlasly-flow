from __future__ import annotations

from datetime import datetime

from scripts.stage0.foundation_service import AuthContext
from scripts.stage0.foundation_service import Stage0RequestError
from scripts.stage0.foundation_service import Stage0Store
from scripts.stage0.foundation_service import get_project_timeline
from scripts.stage0.foundation_service import patch_permits
from scripts.stage0.foundation_service import patch_tasks
from scripts.stage0.foundation_service import post_org_user_invite
from scripts.stage0.foundation_service import post_orgs
from scripts.stage0.foundation_service import post_project_documents
from scripts.stage0.foundation_service import post_project_permits
from scripts.stage0.foundation_service import post_project_tasks
from scripts.stage0.foundation_service import post_projects


def _request_id(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    return headers.get("X-Request-Id")


def _trace_id(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    return headers.get("X-Trace-Id")


def _idempotency_key(headers: dict[str, str] | None) -> str:
    if not headers:
        return ""
    return headers.get("Idempotency-Key", "")


def _if_match(headers: dict[str, str] | None) -> int:
    if not headers:
        raise Stage0RequestError(412, "precondition_failed", "If-Match header is required")
    value = str(headers.get("If-Match") or "").replace('"', "").strip()
    if not value:
        raise Stage0RequestError(412, "precondition_failed", "If-Match header is required")
    try:
        return int(value)
    except ValueError as exc:
        raise Stage0RequestError(422, "validation_failed", "If-Match must be an integer version") from exc


def _error_response(exc: Stage0RequestError) -> tuple[int, dict]:
    return exc.status, {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }


def post_orgs_api(
    *,
    request_body: dict | None,
    headers: dict[str, str] | None,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_orgs(
            request_body=request_body or {},
            idempotency_key=_idempotency_key(headers),
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def post_org_user_invite_api(
    *,
    org_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_org_user_invite(
            org_id=org_id,
            request_body=request_body or {},
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def post_projects_api(
    *,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_projects(
            request_body=request_body or {},
            idempotency_key=_idempotency_key(headers),
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def post_project_permits_api(
    *,
    project_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_project_permits(
            project_id=project_id,
            request_body=request_body or {},
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def post_project_documents_api(
    *,
    project_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_project_documents(
            project_id=project_id,
            request_body=request_body or {},
            idempotency_key=_idempotency_key(headers),
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def post_project_tasks_api(
    *,
    project_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return post_project_tasks(
            project_id=project_id,
            request_body=request_body or {},
            idempotency_key=_idempotency_key(headers),
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def patch_tasks_api(
    *,
    task_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return patch_tasks(
            task_id=task_id,
            request_body=request_body or {},
            if_match_version=_if_match(headers),
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def patch_permits_api(
    *,
    permit_id: str,
    request_body: dict | None,
    headers: dict[str, str] | None,
    auth_context: AuthContext,
    store: Stage0Store,
    now: datetime | None = None,
) -> tuple[int, dict]:
    try:
        return patch_permits(
            permit_id=permit_id,
            request_body=request_body or {},
            auth_context=auth_context,
            store=store,
            now=now,
            request_id=_request_id(headers),
            trace_id=_trace_id(headers),
        )
    except Stage0RequestError as exc:
        return _error_response(exc)


def get_project_timeline_api(
    *,
    project_id: str,
    query_params: dict | None,
    auth_context: AuthContext,
    store: Stage0Store,
) -> tuple[int, dict]:
    try:
        return get_project_timeline(
            project_id=project_id,
            query_params=query_params,
            auth_context=auth_context,
            store=store,
        )
    except Stage0RequestError as exc:
        return _error_response(exc)

