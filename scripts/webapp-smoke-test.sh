#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${ATLASLY_PORT:-8081}"
HOST="${ATLASLY_HOST:-127.0.0.1}"
BASE_URL="http://${HOST}:${PORT}"
LOG_FILE="${TMPDIR:-/tmp}/atlasly-webapp-smoke.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

ATLASLY_HOST="${HOST}" ATLASLY_PORT="${PORT}" PYTHONUNBUFFERED=1 python3 scripts/webapp_server.py >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 120); do
  if curl -sSf "${BASE_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

curl -sSf "${BASE_URL}/api/health" >/dev/null
curl -sSf "${BASE_URL}/api/readiness" >/dev/null

post_json() {
  local path="$1"
  local payload="$2"
  curl -sSf -X POST "${BASE_URL}${path}" -H "Content-Type: application/json" -H "Authorization: Bearer ${AUTH_TOKEN}" -d "${payload}"
}

get_json() {
  local path="$1"
  curl -sSf "${BASE_URL}${path}" -H "Authorization: Bearer ${AUTH_TOKEN}"
}

bootstrap_resp="$(curl -sSf -X POST "${BASE_URL}/api/bootstrap" -H "Content-Type: application/json" -d '{}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True' <<<"${bootstrap_resp}"
AUTH_TOKEN="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session",{}).get("token",""))' <<<"${bootstrap_resp}")"
if [[ -z "${AUTH_TOKEN}" ]]; then
  AUTH_TOKEN="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("sessions") or [{}])[0].get("token",""))' <<<"${bootstrap_resp}")"
fi
if [[ -z "${AUTH_TOKEN}" ]]; then
  echo "Missing session token in bootstrap response"
  exit 1
fi

sessions_resp="$(get_json "/api/sessions")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("bootstrapped") is True; assert len(d.get("sessions", [])) >= 5' <<<"${sessions_resp}"
runtime_diag_resp="$(get_json "/api/runtime-diagnostics")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "runtime" in d; assert "readiness" in d; assert "session_health" in d' <<<"${runtime_diag_resp}"
demo_start_resp="$(curl -sSf -X POST "${BASE_URL}/api/demo/start" -H "Content-Type: application/json" -d '{}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("seeded") is True' <<<"${demo_start_resp}"
feedback_resp="$(post_json "/api/feedback" '{"message":"smoke feedback","rating":5,"category":"smoke"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("id") and d.get("rating")==5' <<<"${feedback_resp}"
telemetry_post_resp="$(post_json "/api/telemetry" '{"event_type":"smoke.test","level":"info","payload":{"phase":"start"}}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("event_type")=="smoke.test"' <<<"${telemetry_post_resp}"
telemetry_get_resp="$(get_json "/api/telemetry?limit=10")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d.get("items", []), list)' <<<"${telemetry_get_resp}"

portfolio_resp="$(get_json "/api/portfolio")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True; assert "kpis" in d; assert isinstance(d.get("projects", []), list)' <<<"${portfolio_resp}"

permit_ops_initial="$(get_json "/api/permit-ops")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True; assert "connector_health" in d; assert "transition_review_queue" in d' <<<"${permit_ops_initial}"

enterprise_overview_initial="$(get_json "/api/enterprise/overview")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True; assert "webhooks" in d; assert "connector_runs" in d' <<<"${enterprise_overview_initial}"

enterprise_webhook_resp="$(post_json "/api/enterprise/webhooks" '{"target_url":"https://hooks.example.com/atlasly","event_types":["permit.status_changed","task.created"]}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("subscription_id")' <<<"${enterprise_webhook_resp}"

enterprise_delivery_resp="$(post_json "/api/enterprise/webhook-delivery" '{"attempt":7,"response_code":503,"error_code":"upstream_timeout","error_detail":"smoke-test"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="dead_lettered"' <<<"${enterprise_delivery_resp}"
enterprise_delivery_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("delivery_id",""))' <<<"${enterprise_delivery_resp}")"
if [[ -n "${enterprise_delivery_id}" ]]; then
  enterprise_replay_resp="$(post_json "/api/enterprise/webhook-replay" "{\"delivery_id\":\"${enterprise_delivery_id}\",\"reason\":\"smoke-test replay\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="queued"' <<<"${enterprise_replay_resp}"
fi

enterprise_connector_sync_resp="$(post_json "/api/enterprise/connector-sync" '{"connector_name":"accela_api","run_mode":"delta"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("run_id")' <<<"${enterprise_connector_sync_resp}"
enterprise_connector_run_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("run_id",""))' <<<"${enterprise_connector_sync_resp}")"
if [[ -n "${enterprise_connector_run_id}" ]]; then
  enterprise_connector_complete_resp="$(post_json "/api/enterprise/connector-complete" "{\"run_id\":\"${enterprise_connector_run_id}\",\"final_status\":\"succeeded\",\"records_fetched\":10,\"records_synced\":10,\"records_failed\":0}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("run_status")=="succeeded"' <<<"${enterprise_connector_complete_resp}"
fi

enterprise_api_key_resp="$(post_json "/api/enterprise/api-keys" '{"name":"smoke key","scopes":["dashboard:read","webhooks:read"]}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("credential_id")' <<<"${enterprise_api_key_resp}"
enterprise_credential_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("credential_id",""))' <<<"${enterprise_api_key_resp}")"
if [[ -n "${enterprise_credential_id}" ]]; then
  enterprise_mark_used_resp="$(post_json "/api/enterprise/api-keys/mark-used" "{\"credential_id\":\"${enterprise_credential_id}\",\"usage_source\":\"smoke-test\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("last_used_at")' <<<"${enterprise_mark_used_resp}"
  enterprise_policy_resp="$(post_json "/api/enterprise/api-keys/policy-scan" '{"max_age_days":90,"warning_days":14,"auto_revoke_overdue":false}')"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert "counts" in d' <<<"${enterprise_policy_resp}"
  enterprise_rotate_resp="$(post_json "/api/enterprise/api-keys/rotate" "{\"credential_id\":\"${enterprise_credential_id}\",\"name\":\"smoke key rotated\",\"scopes\":[\"dashboard:read\"]}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("credential_id")' <<<"${enterprise_rotate_resp}"
  rotated_credential_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("credential_id",""))' <<<"${enterprise_rotate_resp}")"
  if [[ -n "${rotated_credential_id}" ]]; then
    enterprise_revoke_resp="$(post_json "/api/enterprise/api-keys/revoke" "{\"credential_id\":\"${rotated_credential_id}\",\"reason\":\"smoke revoke\"}")"
    python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("revoked_at")' <<<"${enterprise_revoke_resp}"
  fi
fi

enterprise_template_resp="$(post_json "/api/enterprise/task-templates" '{"name":"Smoke Template","description":"smoke","template":{"steps":["collect","submit"]}}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("template_id")' <<<"${enterprise_template_resp}"
enterprise_template_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("template_id",""))' <<<"${enterprise_template_resp}")"
if [[ -n "${enterprise_template_id}" ]]; then
  enterprise_template_archive_resp="$(post_json "/api/enterprise/task-templates/archive" "{\"template_id\":\"${enterprise_template_id}\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("is_active") is False' <<<"${enterprise_template_archive_resp}"
fi

enterprise_export_req_resp="$(post_json "/api/enterprise/audit-exports/request" '{"export_type":"audit_timeline"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("export_id")' <<<"${enterprise_export_req_resp}"
enterprise_export_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("export_id",""))' <<<"${enterprise_export_req_resp}")"
if [[ -n "${enterprise_export_id}" ]]; then
  enterprise_export_run_resp="$(post_json "/api/enterprise/audit-exports/run" "{\"export_id\":\"${enterprise_export_id}\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="running"' <<<"${enterprise_export_run_resp}"
  enterprise_export_done_resp="$(post_json "/api/enterprise/audit-exports/complete" "{\"export_id\":\"${enterprise_export_id}\",\"checksum\":\"sha256:smoke\",\"storage_uri\":\"s3://atlasly/smoke.json\",\"access_log_ref\":\"smoke-log\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="completed"' <<<"${enterprise_export_done_resp}"
  enterprise_evidence_resp="$(get_json "/api/enterprise/audit-evidence?export_id=${enterprise_export_id}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("evidence_pack_id")' <<<"${enterprise_evidence_resp}"
fi

enterprise_snapshot_resp="$(post_json "/api/enterprise/dashboard-snapshot" '{"connector_health_score":93.0,"webhook_delivery_success_rate":0.997}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("snapshot_id")' <<<"${enterprise_snapshot_resp}"

enterprise_dashboard_resp="$(get_json "/api/enterprise/dashboard")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "metrics" in d; assert "freshness_seconds" in d' <<<"${enterprise_dashboard_resp}"

enterprise_webhook_events_resp="$(get_json "/api/enterprise/webhook-events?limit=20")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "items" in d; assert d.get("count",0) >= 1' <<<"${enterprise_webhook_events_resp}"

enterprise_overview_after="$(get_json "/api/enterprise/overview?limit=20")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["webhooks"]["total"] >= 1; assert d["connector_runs"]["total"] >= 1; assert d["api_credentials"]["total"] >= 1; assert d["task_templates"]["total"] >= 1; assert d["audit_exports"]["total"] >= 1' <<<"${enterprise_overview_after}"

enterprise_alerts_resp="$(get_json "/api/enterprise/alerts")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("metrics") is not None; assert isinstance(d.get("alerts", []), list)' <<<"${enterprise_alerts_resp}"
enterprise_slo_resp="$(get_json "/api/enterprise/slo")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "webhook" in d; assert "connectors" in d; assert "transition_reviews" in d; assert "payout_reconciliation" in d' <<<"${enterprise_slo_resp}"
enterprise_readiness_resp="$(get_json "/api/enterprise/integrations-readiness")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "overall_ready" in d; assert "launch_blockers" in d; assert "stage2" in d; assert "stage3" in d' <<<"${enterprise_readiness_resp}"
enterprise_launch_readiness_resp="$(get_json "/api/enterprise/launch-readiness")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "overall_ready" in d; assert "checklist" in d; assert "blockers" in d' <<<"${enterprise_launch_readiness_resp}"

stage2_resolve_ahj_resp="$(post_json "/api/stage2/resolve-ahj" '{"address":{"line1":"200 Market St","city":"San Jose","state":"CA","postal_code":"95113"}}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "resolved" in d' <<<"${stage2_resolve_ahj_resp}"

stage2_rotate_credential_resp="$(post_json "/api/stage2/connector-credentials/rotate" '{"connector":"accela_api","credential_ref":"smoke_live","auth_scheme":"bearer"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("credential", {}).get("credential_ref") == "smoke_live"' <<<"${stage2_rotate_credential_resp}"

stage2_credentials_list_resp="$(get_json "/api/stage2/connector-credentials?connector=accela_api")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("count", 0) >= 1' <<<"${stage2_credentials_list_resp}"
stage2_validate_body_file="$(mktemp)"
stage2_validate_code="$(
  curl -s -o "${stage2_validate_body_file}" -w '%{http_code}' \
    -X POST "${BASE_URL}/api/stage2/connector-validate" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    -d '{"connector":"accela_api","ahj_id":"ca.san_jose.building","credential_ref":"smoke_live"}'
)"
if [[ "${stage2_validate_code}" != "200" && "${stage2_validate_code}" != "400" && "${stage2_validate_code}" != "502" ]]; then
  echo "Unexpected connector validate status: ${stage2_validate_code}"
  cat "${stage2_validate_body_file}"
  rm -f "${stage2_validate_body_file}"
  exit 1
fi
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("validation_status") in {"failed","warning","validated"}; assert d.get("operator_message")' <"${stage2_validate_body_file}"
rm -f "${stage2_validate_body_file}"

stage1_parse_resp="$(post_json "/api/stage1a/parse" '{"text":"Revise panel schedule per NEC 408.4.\nProvide duct sizing report per IMC 603.2."}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("letter_id"); assert len(d.get("extractions", [])) >= 1' <<<"${stage1_parse_resp}"
stage1_quality_resp="$(get_json "/api/stage1a/quality-report?target=staging")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "release_gate" in d; assert "metrics" in d' <<<"${stage1_quality_resp}"

stage1_tasks_resp="$(post_json "/api/stage1a/approve-and-create-tasks" '{}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["task_result"]["created_count"] >= 1' <<<"${stage1_tasks_resp}"
stage1_routing_audit_resp="$(get_json "/api/stage1b/routing-audit?limit=20")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "summary" in d; assert "items" in d' <<<"${stage1_routing_audit_resp}"
stage1_tick_resp="$(post_json "/api/stage1b/escalation-tick" '{"tick_key":"smoke-stage1b-tick","user_mode":"immediate"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "processed_events" in d' <<<"${stage1_tick_resp}"

stage2_intake_resp="$(post_json "/api/stage2/intake-complete" '{"permit_type":"commercial_ti"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("application", {}).get("application_id")' <<<"${stage2_intake_resp}"

stage2_poll_resp="$(post_json "/api/stage2/poll-status" '{"raw_status":"Under review"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("poll_result", {}).get("observations_processed", 0) >= 1' <<<"${stage2_poll_resp}"

permit_ops_after_poll="$(get_json "/api/permit-ops?limit=10")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["transition_review_queue"]["open_count"] >= 1' <<<"${permit_ops_after_poll}"
transition_review_id="$(python3 -c 'import json,sys; d=json.load(sys.stdin); items=d["transition_review_queue"]["items"]; print(items[0]["id"] if items else "")' <<<"${permit_ops_after_poll}")"
if [[ -n "${transition_review_id}" ]]; then
  transition_resolve_resp="$(post_json "/api/permit-ops/resolve-transition" "{\"review_id\":\"${transition_review_id}\",\"resolution_state\":\"resolved\"}")"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["review"]["resolution_state"] == "resolved"' <<<"${transition_resolve_resp}"
fi

stage3_preflight_resp="$(post_json "/api/stage3/preflight" '{}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "risk_score" in d' <<<"${stage3_preflight_resp}"

stage3_payout_resp="$(post_json "/api/stage3/payout" '{"amount":1200}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("instruction_id")' <<<"${stage3_payout_resp}"

if [[ -n "${ATLASLY_STRIPE_SECRET_KEY:-}" ]]; then
  stage3_stripe_payout_resp="$(post_json "/api/stage3/payout" '{"amount":25,"provider":"stripe_sandbox"}')"
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("instruction_id"); assert str(d.get("provider","")).startswith("stripe")' <<<"${stage3_stripe_payout_resp}"
else
  stripe_probe_body_file="$(mktemp)"
  stripe_probe_code="$(
    curl -s -o "${stripe_probe_body_file}" -w '%{http_code}' \
      -X POST "${BASE_URL}/api/stage3/payout" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -d '{"amount":25,"provider":"stripe_sandbox"}'
  )"
  if [[ "${stripe_probe_code}" != "503" ]]; then
    echo "Expected 503 for stripe_sandbox without ATLASLY_STRIPE_SECRET_KEY, got ${stripe_probe_code}"
    cat "${stripe_probe_body_file}"
    rm -f "${stripe_probe_body_file}"
    exit 1
  fi
  python3 -c 'import json,sys; d=json.load(sys.stdin); assert "error" in d' <"${stripe_probe_body_file}"
  rm -f "${stripe_probe_body_file}"
fi

stage3_event_submitted_resp="$(post_json "/api/stage3/provider-event" '{"provider_event_type":"instruction.submitted"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("instruction_state") == "submitted"' <<<"${stage3_event_submitted_resp}"

stage3_event_settled_resp="$(post_json "/api/stage3/provider-event" '{"provider_event_type":"instruction.settled"}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("instruction_state") == "settled"' <<<"${stage3_event_settled_resp}"

stage3_reconcile_resp="$(post_json "/api/stage3/reconcile" '{}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("run_status") in {"matched","mismatched"}' <<<"${stage3_reconcile_resp}"

finance_ops_resp="$(get_json "/api/finance-ops?limit=10")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True; assert d["payouts"]["total"] >= 1; assert "outbox" in d' <<<"${finance_ops_resp}"

publish_resp="$(post_json "/api/stage3/publish-outbox" '{"max_events":200}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "published_count" in d' <<<"${publish_resp}"

summary_resp="$(get_json "/api/summary")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["counts"]["stage1b_tasks"] >= 1; assert d["counts"]["stage3_payout_instructions"] >= 1' <<<"${summary_resp}"

activity_resp="$(get_json "/api/activity?limit=10")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["bootstrapped"] is True; assert isinstance(d.get("events", []), list)' <<<"${activity_resp}"

reset_resp="$(curl -sSf -X POST "${BASE_URL}/api/demo/reset" -H "Content-Type: application/json" -d '{"bootstrap":true}')"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("bootstrapped") is True; assert d.get("session",{}).get("token")' <<<"${reset_resp}"

echo "Webapp smoke test passed."
