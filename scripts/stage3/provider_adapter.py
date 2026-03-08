from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac

from scripts.stage3.payout_api import PayoutRequestError


PROVIDER_STATE_MAP = {
    "instruction.submitted": "submitted",
    "instruction.failed_transient": "failed_transient",
    "instruction.failed_terminal": "failed_terminal",
    "instruction.settled": "settled",
    "instruction.reversed": "reversed",
}


def normalize_provider_status(*, provider_event_type: str) -> str:
    state = PROVIDER_STATE_MAP.get(provider_event_type)
    if not state:
        raise PayoutRequestError(422, "validation_error", "unsupported provider event type")
    return state


def normalize_settlement_row(raw: dict) -> dict:
    if "instruction_id" not in raw or "amount" not in raw or "currency" not in raw:
        raise PayoutRequestError(422, "validation_error", "invalid settlement row")
    return {
        "instruction_id": str(raw["instruction_id"]),
        "amount": float(raw["amount"]),
        "currency": str(raw["currency"]),
        "provider_reference": str(raw.get("provider_reference") or ""),
        "settled_at": str(raw.get("settled_at") or datetime.now(timezone.utc).isoformat()),
    }


def build_provider_signature_payload(*, request_body: dict[str, object]) -> str:
    fields = [
        str(request_body.get("instruction_id") or ""),
        str(request_body.get("provider_event_type") or ""),
        str(request_body.get("provider_reference") or ""),
        str(request_body.get("amount") or ""),
        str(request_body.get("currency") or ""),
    ]
    return "|".join(fields)


def compute_provider_signature(*, secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_provider_signature(
    *,
    request_body: dict[str, object],
    headers: dict[str, str] | None,
    secret: str | None,
    required: bool,
) -> None:
    signature = (headers or {}).get("X-Provider-Signature", "").strip()
    if not required and not signature:
        return
    if not secret:
        raise PayoutRequestError(503, "signature_secret_missing", "provider webhook signing secret not configured")
    if not signature:
        raise PayoutRequestError(401, "signature_missing", "provider webhook signature missing")

    payload = build_provider_signature_payload(request_body=request_body)
    expected = compute_provider_signature(secret=secret, payload=payload)
    if not hmac.compare_digest(signature, expected):
        raise PayoutRequestError(401, "signature_invalid", "provider webhook signature invalid")
