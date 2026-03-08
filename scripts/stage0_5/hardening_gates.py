from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage05OperationalSignals:
    webhook_success_rate_24h_pct: float
    webhook_success_rate_60m_pct: float
    webhook_dlq_growth_30m: int

    connector_run_success_rate_24h_pct: float
    connector_max_staleness_minutes: int

    dashboard_refresh_p95_seconds: int
    dashboard_max_staleness_seconds: int

    api_key_rotation_coverage_pct: float
    audit_export_success_rate_24h_pct: float

    p1_incidents_last_24h: int


def evaluate_release_gates(signals: Stage05OperationalSignals) -> dict:
    gates = [
        {
            "name": "webhook_delivery_success_24h",
            "passed": signals.webhook_success_rate_24h_pct >= 99.0,
            "actual": signals.webhook_success_rate_24h_pct,
            "target": ">=99.0",
        },
        {
            "name": "connector_success_24h",
            "passed": signals.connector_run_success_rate_24h_pct >= 98.5,
            "actual": signals.connector_run_success_rate_24h_pct,
            "target": ">=98.5",
        },
        {
            "name": "dashboard_refresh_p95",
            "passed": signals.dashboard_refresh_p95_seconds <= 300,
            "actual": signals.dashboard_refresh_p95_seconds,
            "target": "<=300s",
        },
        {
            "name": "dashboard_staleness_max",
            "passed": signals.dashboard_max_staleness_seconds <= 300,
            "actual": signals.dashboard_max_staleness_seconds,
            "target": "<=300s",
        },
        {
            "name": "api_key_rotation_coverage",
            "passed": signals.api_key_rotation_coverage_pct >= 95.0,
            "actual": signals.api_key_rotation_coverage_pct,
            "target": ">=95.0",
        },
        {
            "name": "audit_export_success_24h",
            "passed": signals.audit_export_success_rate_24h_pct >= 99.0,
            "actual": signals.audit_export_success_rate_24h_pct,
            "target": ">=99.0",
        },
        {
            "name": "p1_incidents_last_24h",
            "passed": signals.p1_incidents_last_24h == 0,
            "actual": signals.p1_incidents_last_24h,
            "target": "==0",
        },
    ]

    rollback_triggers = [
        {
            "name": "rollback_webhook_success_60m",
            "breached": signals.webhook_success_rate_60m_pct < 97.0,
            "actual": signals.webhook_success_rate_60m_pct,
            "threshold": "<97.0",
        },
        {
            "name": "rollback_webhook_dlq_growth_30m",
            "breached": signals.webhook_dlq_growth_30m > 200,
            "actual": signals.webhook_dlq_growth_30m,
            "threshold": ">200",
        },
        {
            "name": "rollback_connector_staleness",
            "breached": signals.connector_max_staleness_minutes > 120,
            "actual": signals.connector_max_staleness_minutes,
            "threshold": ">120m",
        },
        {
            "name": "rollback_dashboard_staleness",
            "breached": signals.dashboard_max_staleness_seconds > 900,
            "actual": signals.dashboard_max_staleness_seconds,
            "threshold": ">900s",
        },
        {
            "name": "rollback_p1_incidents",
            "breached": signals.p1_incidents_last_24h >= 2,
            "actual": signals.p1_incidents_last_24h,
            "threshold": ">=2",
        },
    ]

    return {
        "ready_for_public_mvp": all(g["passed"] for g in gates),
        "gates": gates,
        "rollback_triggers": rollback_triggers,
        "rollback_required_now": any(t["breached"] for t in rollback_triggers),
    }
