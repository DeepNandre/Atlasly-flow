from __future__ import annotations

from dataclasses import dataclass, field


def required_stage0_5_mvp_contracts() -> tuple[str, ...]:
    return (
        "register_webhook_subscription",
        "list_webhook_events",
        "enqueue_webhook_retry",
        "request_webhook_replay_for_dead_letter",
        "start_connector_run",
        "complete_connector_run",
        "record_connector_error",
        "upsert_dashboard_snapshot",
        "get_latest_dashboard_snapshot",
        "create_api_credential",
        "revoke_api_credential",
        "rotate_api_credential",
        "create_task_template",
        "archive_task_template",
        "request_security_audit_export",
        "mark_security_audit_export_running",
        "mark_security_audit_export_completed",
        "mark_security_audit_export_failed",
    )


@dataclass(frozen=True)
class PersistenceCapabilityReport:
    backend_name: str
    production_ready: bool
    required_contracts: tuple[str, ...]
    missing_contracts: tuple[str, ...]
    notes: str


@dataclass
class InMemoryStage05Adapter:
    backend_name: str = "in_memory"

    def capability_report(self) -> PersistenceCapabilityReport:
        required = required_stage0_5_mvp_contracts()
        return PersistenceCapabilityReport(
            backend_name=self.backend_name,
            production_ready=False,
            required_contracts=required,
            missing_contracts=required,
            notes=(
                "NOT PRODUCTION READY: in-memory adapter loses state on process restart and "
                "must not be used for public MVP operations."
            ),
        )


@dataclass
class SqlFunctionStage05Adapter:
    dsn: str | None
    backend_name: str = "sql_functions"
    discovered_contracts: set[str] = field(default_factory=set)

    def capability_report(self) -> PersistenceCapabilityReport:
        required = required_stage0_5_mvp_contracts()
        missing = tuple(sorted(set(required) - set(self.discovered_contracts)))
        ready = bool(self.dsn and not missing)
        return PersistenceCapabilityReport(
            backend_name=self.backend_name,
            production_ready=ready,
            required_contracts=required,
            missing_contracts=missing,
            notes=(
                "Production-capable when DSN is configured and all required Stage 0.5 SQL "
                "contracts are discoverable in the target environment."
            ),
        )
