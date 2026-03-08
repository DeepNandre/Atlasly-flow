# Stage 3 Security Hardening (Webhook Signature Verification)

## Scope
- Added provider webhook signature verification helpers for Stage 3 runtime webhook ingestion.
- Supports optional and enforced modes.

## Environment controls
- `ATLASLY_STAGE3_PROVIDER_WEBHOOK_SECRET`
- `ATLASLY_STAGE3_ENFORCE_SIGNATURES` (`true|false`)

## Header contract
- Header: `X-Provider-Signature`
- Format: `sha256=<hex_hmac>`

## Signing payload
Concatenated fields:
1. `instruction_id`
2. `provider_event_type`
3. `provider_reference`
4. `amount`
5. `currency`

Joined with `|` before HMAC-SHA256.

## Files
- `scripts/stage3/provider_adapter.py`
- `scripts/stage3/runtime_api.py`
- `tests/stage3/test_stage3_slice8_runtime_endpoints.py`
