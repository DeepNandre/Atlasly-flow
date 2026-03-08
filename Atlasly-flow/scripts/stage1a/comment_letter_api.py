from __future__ import annotations

import uuid

from scripts.stage1a.comment_extraction_service import AuthContext
from scripts.stage1a.comment_extraction_service import Stage1ARequestError
from scripts.stage1a.comment_extraction_service import Stage1AStore
from scripts.stage1a.comment_extraction_service import approve_comment_letter
from scripts.stage1a.comment_extraction_service import create_comment_letter
from scripts.stage1a.comment_extraction_service import get_comment_letter_status
from scripts.stage1a.comment_extraction_service import list_comment_extractions


def _assert_uuid(raw: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(str(raw)))
    except Exception as exc:  # noqa: BLE001
        raise Stage1ARequestError(422, "validation_error", f"{field_name} must be a valid UUID") from exc


def post_comment_letters(
    *,
    request_body: dict[str, object] | None,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
) -> tuple[int, dict]:
    body = request_body or {}
    project_id = _assert_uuid(str(body.get("project_id") or ""), "project_id")
    document_id = _assert_uuid(str(body.get("document_id") or ""), "document_id")
    source_filename = body.get("source_filename")
    source_name = str(source_filename) if source_filename is not None else None

    return create_comment_letter(
        project_id=project_id,
        document_id=document_id,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        auth_context=auth_context,
        store=store,
        source_filename=source_name,
    )


def get_comment_letter(
    *,
    letter_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
) -> tuple[int, dict]:
    normalized_letter_id = _assert_uuid(letter_id, "letterId")
    return get_comment_letter_status(letter_id=normalized_letter_id, auth_context=auth_context, store=store)


def get_comment_letter_extractions(
    *,
    letter_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
) -> tuple[int, dict]:
    normalized_letter_id = _assert_uuid(letter_id, "letterId")
    return list_comment_extractions(letter_id=normalized_letter_id, auth_context=auth_context, store=store)


def post_comment_letter_approve(
    *,
    letter_id: str,
    request_body: dict[str, object] | None,
    trace_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
) -> tuple[int, dict]:
    normalized_letter_id = _assert_uuid(letter_id, "letterId")
    # The approving actor is always the authenticated user identity.
    # Client-supplied approved_by is intentionally ignored to prevent spoofing.
    _ = request_body or {}
    if not auth_context.user_id:
        raise Stage1ARequestError(401, "unauthorized", "authenticated user identity is required")
    try:
        uuid.UUID(str(auth_context.user_id))
    except Exception as exc:  # noqa: BLE001
        raise Stage1ARequestError(401, "unauthorized", "authenticated user identity is invalid") from exc

    return approve_comment_letter(
        letter_id=normalized_letter_id,
        trace_id=trace_id,
        auth_context=auth_context,
        store=store,
    )
