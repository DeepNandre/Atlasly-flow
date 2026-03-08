#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${ATLASLY_PORT:-8091}"
HOST="${ATLASLY_HOST:-127.0.0.1}"
SERVER_LOG="${TMPDIR:-/tmp}/atlasly-frontend-smoke-server.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT/frontend"
npm run build >/dev/null

cd "$ROOT"
ATLASLY_HOST="$HOST" ATLASLY_PORT="$PORT" PYTHONUNBUFFERED=1 python3 scripts/webapp_server.py >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

INDEX_HTML="$(curl -fsS "http://$HOST:$PORT/")"
[[ "$INDEX_HTML" == *"/assets/index-"* ]]

for route in / /letters /tasks /permits /integrations /settings; do
  HTML="$(curl -fsS "http://$HOST:$PORT$route")"
  [[ "$HTML" == *"<div id=\"root\"></div>"* ]]
done

BOOTSTRAP_PAYLOAD="$(curl -fsS -X POST "http://$HOST:$PORT/api/bootstrap" -H 'Content-Type: application/json' -d '{}')"
TOKEN="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print((d.get("session") or {}).get("token") or ((d.get("sessions") or [{}])[0].get("token","")))' "$BOOTSTRAP_PAYLOAD")"
[[ -n "$TOKEN" ]]

curl -fsS "http://$HOST:$PORT/api/portfolio" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -fsS "http://$HOST:$PORT/api/stage1a/letters" -H "Authorization: Bearer $TOKEN" >/dev/null
curl -fsS "http://$HOST:$PORT/api/stage1b/tasks" -H "Authorization: Bearer $TOKEN" >/dev/null

printf 'Frontend browser smoke test passed.\n'
