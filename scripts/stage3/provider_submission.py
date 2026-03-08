from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen
import uuid

from scripts.stage3.payout_api import PayoutRequestError


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _submit_stripe_payment_intent(
    *,
    instruction: dict,
    stripe_secret_key: str,
    base_url: str,
) -> dict:
    amount_cents = int(round(float(instruction["amount"]) * 100))
    if amount_cents <= 0:
        raise PayoutRequestError(422, "validation_error", "amount must be positive for provider submission")

    form = urlencode(
        {
            "amount": str(amount_cents),
            "currency": str(instruction["currency"]).lower(),
            "confirm": "false",
            "capture_method": "automatic",
            "metadata[instruction_id]": instruction["instruction_id"],
            "metadata[milestone_id]": instruction["milestone_id"],
            "description": f"Atlasly payout instruction {instruction['instruction_id']}",
        }
    ).encode("utf-8")
    url = f"{base_url.rstrip('/')}/v1/payment_intents"
    request = Request(
        url=url,
        method="POST",
        data=form,
        headers={
            "Authorization": f"Bearer {stripe_secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": f"atlasly:{instruction['instruction_id']}",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        code = int(exc.code)
        retryable = code >= 500 or code in {408, 409, 429}
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            body = ""
        message = f"stripe sandbox rejected request ({code})"
        if body:
            message = f"{message}: {body[:200]}"
        raise PayoutRequestError(503 if retryable else 424, "provider_rejected", message) from exc
    except URLError as exc:
        raise PayoutRequestError(503, "provider_unavailable", f"stripe sandbox network error: {exc.reason}") from exc

    intent_id = str(payload.get("id") or "").strip()
    if not intent_id:
        raise PayoutRequestError(424, "provider_rejected", "stripe response missing payment intent id")

    return {
        "accepted": True,
        "provider_event_type": "instruction.submitted",
        "provider_reference": intent_id,
        "submitted_at": _iso_now(),
    }


def submit_provider_instruction(
    *,
    instruction: dict,
    stripe_secret_key: str | None,
    stripe_base_url: str = "https://api.stripe.com",
) -> dict:
    provider = str(instruction.get("provider") or "").strip().lower()
    if provider in {"provider_sandbox", "demo_sandbox"}:
        return {
            "accepted": True,
            "provider_event_type": "instruction.submitted",
            "provider_reference": f"sandbox-{uuid.uuid4().hex[:12]}",
            "submitted_at": _iso_now(),
        }

    if provider in {"stripe", "stripe_connect", "stripe_sandbox", "stripe_connect_sandbox"}:
        key = str(stripe_secret_key or "").strip()
        if not key:
            raise PayoutRequestError(503, "provider_unavailable", "stripe secret key missing for sandbox submission")
        return _submit_stripe_payment_intent(
            instruction=instruction,
            stripe_secret_key=key,
            base_url=stripe_base_url,
        )

    raise PayoutRequestError(422, "validation_error", f"unsupported payout provider: {provider}")
