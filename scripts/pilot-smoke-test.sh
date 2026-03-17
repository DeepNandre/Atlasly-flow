#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/atlasly-pilot-smoke.XXXXXX")"
PORT="${ATLASLY_PORT:-8094}"
HOST="${ATLASLY_HOST:-127.0.0.1}"
BASE_URL="http://${HOST}:${PORT}"
LOG_FILE="${TMPDIR:-/tmp}/atlasly-pilot-smoke.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  rm -rf "${DATA_DIR}"
}
trap cleanup EXIT

start_server() {
  ATLASLY_HOST="${HOST}" \
  ATLASLY_PORT="${PORT}" \
  ATLASLY_DEPLOYMENT_TIER="mvp" \
  ATLASLY_STAGE05_RUNTIME_BACKEND="sqlite" \
  ATLASLY_STAGE05_PERSISTENCE_READY="true" \
  ATLASLY_DATA_DIR="${DATA_DIR}" \
  PYTHONUNBUFFERED=1 \
  python3 scripts/webapp_server.py >"${LOG_FILE}" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do
    if curl -sSf "${BASE_URL}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  echo "pilot smoke: server failed to start"
  cat "${LOG_FILE}" || true
  exit 1
}

bootstrap_and_token() {
  local boot
  boot="$(curl -sSf -X POST "${BASE_URL}/api/bootstrap" -H "Content-Type: application/json" -d '{}')"
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print("|".join([d["sessions"][0]["token"], d["ids"]["organization_id"], str(d["runtime"]["demo_routes_enabled"]).lower()]))' "${boot}"
}

start_server
BOOT_DATA="$(bootstrap_and_token)"
AUTH_TOKEN="$(printf '%s' "${BOOT_DATA}" | cut -d'|' -f1)"
ORG_ID="$(printf '%s' "${BOOT_DATA}" | cut -d'|' -f2)"
DEMO_ENABLED="$(printf '%s' "${BOOT_DATA}" | cut -d'|' -f3)"

if [[ "${DEMO_ENABLED}" != "false" ]]; then
  echo "pilot smoke: demo routes unexpectedly enabled"
  exit 1
fi

curl -sSf -X POST "${BASE_URL}/api/feedback" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -d '{"message":"pilot persistence check","rating":5,"category":"ops"}' >/dev/null

SUMMARY_ONE="$(curl -sSf "${BASE_URL}/api/summary" -H "Authorization: Bearer ${AUTH_TOKEN}")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["counts"]["feedback_entries"] == 1; assert d["runtime"]["deployment_tier"] == "mvp"' "${SUMMARY_ONE}"

DEMO_RESET_CODE="$(curl -s -o /tmp/atlasly-pilot-reset.out -w "%{http_code}" -X POST "${BASE_URL}/api/demo/reset" -H "Content-Type: application/json" -d '{}')"
if [[ "${DEMO_RESET_CODE}" != "403" ]]; then
  echo "pilot smoke: expected /api/demo/reset to be blocked in mvp tier"
  cat /tmp/atlasly-pilot-reset.out || true
  exit 1
fi

POLL_CODE="$(curl -s -o /tmp/atlasly-pilot-poll.out -w "%{http_code}" -X POST "${BASE_URL}/api/stage2/poll-live" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -d '{"connector":"accela_api","ahj_id":"ca.san_jose.building"}')"
if [[ "${POLL_CODE}" != "422" && "${POLL_CODE}" != "503" ]]; then
  echo "pilot smoke: expected live poll to fail clearly without configured creds"
  cat /tmp/atlasly-pilot-poll.out || true
  exit 1
fi

kill "${SERVER_PID}" 2>/dev/null || true
wait "${SERVER_PID}" 2>/dev/null || true
unset SERVER_PID

start_server
BOOT_DATA_RESTART="$(bootstrap_and_token)"
AUTH_TOKEN_RESTART="$(printf '%s' "${BOOT_DATA_RESTART}" | cut -d'|' -f1)"
ORG_ID_RESTART="$(printf '%s' "${BOOT_DATA_RESTART}" | cut -d'|' -f2)"

SUMMARY_TWO="$(curl -sSf "${BASE_URL}/api/summary" -H "Authorization: Bearer ${AUTH_TOKEN_RESTART}")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["counts"]["feedback_entries"] == 1' "${SUMMARY_TWO}"
if [[ "${ORG_ID}" != "${ORG_ID_RESTART}" ]]; then
  echo "pilot smoke: org id changed across restart"
  exit 1
fi

echo "Pilot smoke checks passed."
