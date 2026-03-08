#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${ATLASLY_PORT:-8082}"
HOST="${ATLASLY_HOST:-127.0.0.1}"
BASE_URL="http://${HOST}:${PORT}"
STRICT_MODE="${ATLASLY_LIVE_VALIDATION_STRICT:-0}"
LOG_FILE="${TMPDIR:-/tmp}/atlasly-live-validations.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

ATLASLY_HOST="${HOST}" ATLASLY_PORT="${PORT}" PYTHONUNBUFFERED=1 python3 scripts/webapp_server.py >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -sSf "${BASE_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

curl -sSf "${BASE_URL}/api/health" >/dev/null

bootstrap_resp="$(curl -sSf -X POST "${BASE_URL}/api/bootstrap" -H "Content-Type: application/json" -d '{}')"
AUTH_TOKEN="$(
  python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("session") or {}).get("token") or d.get("token") or ((d.get("sessions") or [{}])[0].get("token","")))' <<<"${bootstrap_resp}"
)"
INTERNAL_PERMIT_ID="$(
  python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("ids") or {}).get("permit_id",""))' <<<"${bootstrap_resp}"
)"
if [[ -z "${AUTH_TOKEN}" ]]; then
  echo "Missing session token in bootstrap response"
  exit 1
fi

post_json() {
  local path="$1"
  local payload="$2"
  curl -sSf -X POST "${BASE_URL}${path}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    -d "${payload}"
}

get_json() {
  local path="$1"
  curl -sSf "${BASE_URL}${path}" -H "Authorization: Bearer ${AUTH_TOKEN}"
}

echo "== Integration readiness =="
get_json "/api/enterprise/integrations-readiness" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"overall_ready":d.get("overall_ready"),"blockers":d.get("launch_blockers",[])}, indent=2))'

echo
echo "== Stage 2 live connector validation =="
LIVE_CONNECTOR="${ATLASLY_LIVE_CONNECTOR:-accela_api}"
LIVE_AHJ_ID="${ATLASLY_LIVE_AHJ_ID:-ca.san_jose.building}"
LIVE_CREDENTIAL_REF="${ATLASLY_LIVE_CREDENTIAL_REF:-}"
LIVE_EXTERNAL_PERMIT_ID="${ATLASLY_LIVE_EXTERNAL_PERMIT_ID:-}"

if [[ -n "${LIVE_CREDENTIAL_REF}" ]]; then
  SECRET_ENV_NAME="$(
    python3 -c 'import re,sys; print("ATLASLY_CONNECTOR_SECRET_" + re.sub(r"[^A-Z0-9_]", "_", sys.argv[1].upper()))' "${LIVE_CREDENTIAL_REF}"
  )"
  if [[ -z "${!SECRET_ENV_NAME:-}" ]]; then
    echo "Missing connector secret env ${SECRET_ENV_NAME} for credential ref ${LIVE_CREDENTIAL_REF}"
    if [[ "${STRICT_MODE}" == "1" ]]; then
      exit 1
    fi
  else
    post_json "/api/stage2/connector-credentials/rotate" "$(python3 -c 'import json,sys; print(json.dumps({"connector":sys.argv[1],"credential_ref":sys.argv[2],"auth_scheme":"bearer"}))' "${LIVE_CONNECTOR}" "${LIVE_CREDENTIAL_REF}")" >/dev/null
    if [[ -n "${LIVE_EXTERNAL_PERMIT_ID}" && -n "${INTERNAL_PERMIT_ID}" ]]; then
      post_json "/api/stage2/permit-bindings" "$(python3 -c 'import json,sys; print(json.dumps({"connector":sys.argv[1],"ahj_id":sys.argv[2],"permit_id":sys.argv[3],"external_permit_id":sys.argv[4]}))' "${LIVE_CONNECTOR}" "${LIVE_AHJ_ID}" "${INTERNAL_PERMIT_ID}" "${LIVE_EXTERNAL_PERMIT_ID}")" >/dev/null
    fi
    poll_resp="$(post_json "/api/stage2/poll-live" "$(python3 -c 'import json,sys; print(json.dumps({"connector":sys.argv[1],"ahj_id":sys.argv[2]}))' "${LIVE_CONNECTOR}" "${LIVE_AHJ_ID}")")"
    python3 -c 'import json,sys; d=json.load(sys.stdin); run=d.get("poll_result",{}).get("run",{}); payload={"connector_run_status":run.get("status"),"observations_processed":d.get("poll_result",{}).get("observations_processed"),"observations_applied":d.get("poll_result",{}).get("observations_applied"),"observations_reviewed":d.get("poll_result",{}).get("observations_reviewed"),"unmapped_observations":len(d.get("poll_result",{}).get("unmapped_observations",[]))}; print(json.dumps(payload, indent=2)); assert run.get("status") in {"succeeded","partial"}; strict=(sys.argv[1]=="1"); assert (not strict) or payload["connector_run_status"]=="succeeded"' "${STRICT_MODE}" <<<"${poll_resp}"
  fi
else
  echo "Skipping Stage 2 live poll (set ATLASLY_LIVE_CREDENTIAL_REF and corresponding secret env var)."
  if [[ "${STRICT_MODE}" == "1" ]]; then
    exit 1
  fi
fi

echo
echo "== Stage 3 stripe sandbox validation =="
STRIPE_ENABLED="${ATLASLY_ENABLE_STRIPE:-0}"
ENFORCE_SIGNATURES="${ATLASLY_STAGE3_ENFORCE_SIGNATURES:-0}"
if [[ -n "${ATLASLY_STRIPE_SECRET_KEY:-}" || "${STRIPE_ENABLED}" == "1" || "${STRIPE_ENABLED}" == "true" || "${ENFORCE_SIGNATURES}" == "1" || "${ENFORCE_SIGNATURES}" == "true" ]]; then
  stripe_resp="$(post_json "/api/stage3/payout" '{"amount":25,"provider":"stripe_sandbox","currency":"USD","beneficiary_id":"beneficiary-live-validation"}')"
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"instruction_id":d.get("instruction_id"),"provider":d.get("provider"),"state":d.get("instruction_state")}, indent=2)); assert d.get("instruction_id")' <<<"${stripe_resp}"
else
  echo "Skipping Stripe sandbox payout (set ATLASLY_STRIPE_SECRET_KEY)."
fi

echo
echo "Live validation checks completed."
