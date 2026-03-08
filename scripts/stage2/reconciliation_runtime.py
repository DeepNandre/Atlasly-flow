from __future__ import annotations

from datetime import datetime, timezone

from scripts.stage2.repositories import Stage2Repository
from scripts.stage2.status_sync import classify_drift
from scripts.stage2.status_sync import normalize_status


def run_permit_reconciliation(
    *,
    organization_id: str,
    permit_id: str,
    connector: str | None,
    ahj_id: str | None,
    current_ruleset_version: str,
    previous_ruleset_version: str,
    rules: list[dict] | None,
    repository: Stage2Repository,
    now: datetime | None = None,
) -> dict:
    ts = now or datetime.now(timezone.utc)
    events = repository.list_status_events_by_permit(
        organization_id=organization_id,
        permit_id=permit_id,
    )
    if not events:
        run = repository.save_reconciliation_run(
            {
                "organization_id": organization_id,
                "connector": connector,
                "ahj_id": ahj_id,
                "run_started_at": ts.isoformat(),
                "run_finished_at": ts.isoformat(),
                "status": "matched",
                "totals_json": {"checked": 0, "matched": 0, "drifted": 0},
                "mismatch_summary_json": [],
                "ruleset_version": current_ruleset_version,
            }
        )
        return {"run": run, "alerts": []}

    latest = events[0]
    projection = repository.get_status_projection(permit_id)
    projected_status = projection["current_status"] if projection else (latest["normalized_status"] or "submitted")

    recomputed = normalize_status(
        raw_status=latest["raw_status"],
        connector=connector,
        ahj_id=ahj_id,
        rules=rules,
    )
    recomputed_status = recomputed["normalized_status"] or projected_status
    drift_type = classify_drift(
        projected_status=projected_status,
        recomputed_status=recomputed_status,
        previous_ruleset_version=previous_ruleset_version,
        current_ruleset_version=current_ruleset_version,
        previous_payload_hash=latest.get("event_hash"),
        current_payload_hash=latest.get("event_hash"),
    )

    mismatch_summary = []
    alerts = []
    if drift_type:
        mismatch_summary.append(
            {
                "permit_id": permit_id,
                "projected_status": projected_status,
                "recomputed_status": recomputed_status,
                "drift_type": drift_type,
            }
        )
        alerts.append(
            repository.insert_drift_alert(
                {
                    "organization_id": organization_id,
                    "permit_id": permit_id,
                    "connector": connector,
                    "ahj_id": ahj_id,
                    "drift_type": drift_type,
                    "severity": "medium",
                    "status": "open",
                    "details_json": mismatch_summary[-1],
                    "detected_at": ts.isoformat(),
                }
            )
        )

    run = repository.save_reconciliation_run(
        {
            "organization_id": organization_id,
            "connector": connector,
            "ahj_id": ahj_id,
            "run_started_at": ts.isoformat(),
            "run_finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "matched" if not mismatch_summary else "mismatched",
            "totals_json": {
                "checked": len(events),
                "matched": len(events) - len(mismatch_summary),
                "drifted": len(mismatch_summary),
            },
            "mismatch_summary_json": mismatch_summary,
            "ruleset_version": current_ruleset_version,
        }
    )
    return {"run": run, "alerts": alerts}
