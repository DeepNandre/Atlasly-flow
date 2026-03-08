from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.repositories import Stage3Repository


MISMATCH_TYPES = {
    "timing_gap",
    "amount_mismatch",
    "missing_internal",
    "missing_provider",
    "duplicate_provider_event",
}


@dataclass
class FinanceStore:
    financial_events: list[dict]
    reconciliation_runs_by_id: dict[str, dict]

    @classmethod
    def empty(cls) -> "FinanceStore":
        return cls([], {})


def record_financial_event(
    *,
    organization_id: str,
    instruction_id: str,
    milestone_id: str,
    event_type: str,
    amount: float,
    currency: str,
    trace_id: str,
    source_service: str,
    payload: dict,
    occurred_at: datetime,
    store: FinanceStore,
) -> dict:
    event = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "instruction_id": instruction_id,
        "milestone_id": milestone_id,
        "event_type": event_type,
        "amount": round(amount, 2),
        "currency": currency,
        "trace_id": trace_id,
        "source_service": source_service,
        "payload": payload,
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    store.financial_events.append(event)
    return event


def create_reconciliation_run(
    *,
    organization_id: str,
    provider: str,
    provider_settlements: list[dict],
    store: FinanceStore,
    run_started_at: datetime | None = None,
) -> dict:
    started = run_started_at or datetime.now(timezone.utc)

    internal_by_instruction = {}
    for event in store.financial_events:
        if event["organization_id"] != organization_id:
            continue
        instruction_id = event.get("instruction_id")
        if not instruction_id:
            continue
        internal_by_instruction.setdefault(instruction_id, []).append(event)

    settlements_by_instruction = {}
    duplicate_provider = set()
    for settlement in provider_settlements:
        instruction_id = settlement["instruction_id"]
        if instruction_id in settlements_by_instruction:
            duplicate_provider.add(instruction_id)
        settlements_by_instruction[instruction_id] = settlement

    matched_entries: list[dict] = []
    mismatches: list[dict] = []

    for instruction_id, settlement in settlements_by_instruction.items():
        events = internal_by_instruction.get(instruction_id)
        if not events:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "missing_internal",
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        submitted_or_settled = [
            ev
            for ev in events
            if ev["event_type"] in {"instruction_submitted", "provider_settled"}
        ]
        if not submitted_or_settled:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "timing_gap",
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        internal_amount = submitted_or_settled[-1]["amount"]
        provider_amount = round(float(settlement["amount"]), 2)
        if internal_amount != provider_amount:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "amount_mismatch",
                    "internal_amount": internal_amount,
                    "provider_amount": provider_amount,
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        matched_entries.append(
            {
                "instruction_id": instruction_id,
                "provider_reference": settlement.get("provider_reference"),
                "amount": provider_amount,
                "currency": settlement.get("currency"),
            }
        )

    for instruction_id in internal_by_instruction:
        if instruction_id not in settlements_by_instruction:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "missing_provider",
                    "provider_reference": None,
                }
            )

    for instruction_id in duplicate_provider:
        mismatches.append(
            {
                "instruction_id": instruction_id,
                "mismatch_type": "duplicate_provider_event",
                "provider_reference": settlements_by_instruction[instruction_id].get("provider_reference"),
            }
        )

    for mismatch in mismatches:
        if mismatch["mismatch_type"] not in MISMATCH_TYPES:
            raise PayoutRequestError(500, "internal_error", "unknown mismatch type generated")

    run_id = str(uuid.uuid4())
    run = {
        "id": run_id,
        "organization_id": organization_id,
        "provider": provider,
        "run_started_at": started.isoformat(),
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "run_status": "matched" if not mismatches else "mismatched",
        "matched_count": len(matched_entries),
        "mismatched_count": len(mismatches),
        "missing_internal_count": len([m for m in mismatches if m["mismatch_type"] == "missing_internal"]),
        "missing_provider_count": len([m for m in mismatches if m["mismatch_type"] == "missing_provider"]),
        "result_payload": {
            "matched_entries": matched_entries,
            "mismatches": mismatches,
        },
    }
    store.reconciliation_runs_by_id[run_id] = run
    return run


def get_reconciliation_run(*, run_id: str, organization_id: str, store: FinanceStore) -> tuple[int, dict]:
    run = store.reconciliation_runs_by_id.get(run_id)
    if not run:
        raise PayoutRequestError(404, "not_found", "reconciliation run not found")
    if run["organization_id"] != organization_id:
        raise PayoutRequestError(403, "forbidden", "reconciliation run belongs to another organization")
    return 200, run


def record_financial_event_persisted(
    *,
    organization_id: str,
    instruction_id: str,
    milestone_id: str,
    event_type: str,
    amount: float,
    currency: str,
    trace_id: str,
    source_service: str,
    payload: dict,
    occurred_at: datetime,
    repository: Stage3Repository,
) -> dict:
    return repository.append_financial_event(
        {
            "organization_id": organization_id,
            "instruction_id": instruction_id,
            "milestone_id": milestone_id,
            "event_type": event_type,
            "amount": round(amount, 2),
            "currency": currency,
            "trace_id": trace_id,
            "source_service": source_service,
            "payload": payload,
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        }
    )


def create_reconciliation_run_persisted(
    *,
    organization_id: str,
    provider: str,
    provider_settlements: list[dict],
    repository: Stage3Repository,
    run_started_at: datetime | None = None,
) -> dict:
    started = run_started_at or datetime.now(timezone.utc)
    internal_events = repository.list_financial_events_by_org(organization_id)

    internal_by_instruction = {}
    for event in internal_events:
        instruction_id = event.get("instruction_id")
        if not instruction_id:
            continue
        internal_by_instruction.setdefault(instruction_id, []).append(event)

    settlements_by_instruction = {}
    duplicate_provider = set()
    for settlement in provider_settlements:
        instruction_id = settlement["instruction_id"]
        if instruction_id in settlements_by_instruction:
            duplicate_provider.add(instruction_id)
        settlements_by_instruction[instruction_id] = settlement

    matched_entries: list[dict] = []
    mismatches: list[dict] = []

    for instruction_id, settlement in settlements_by_instruction.items():
        events = internal_by_instruction.get(instruction_id)
        if not events:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "missing_internal",
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        submitted_or_settled = [
            ev for ev in events if ev["event_type"] in {"instruction_submitted", "provider_settled"}
        ]
        if not submitted_or_settled:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "timing_gap",
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        internal_amount = submitted_or_settled[-1]["amount"]
        provider_amount = round(float(settlement["amount"]), 2)
        if internal_amount != provider_amount:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "amount_mismatch",
                    "internal_amount": internal_amount,
                    "provider_amount": provider_amount,
                    "provider_reference": settlement.get("provider_reference"),
                }
            )
            continue

        matched_entries.append(
            {
                "instruction_id": instruction_id,
                "provider_reference": settlement.get("provider_reference"),
                "amount": provider_amount,
                "currency": settlement.get("currency"),
            }
        )

    for instruction_id in internal_by_instruction:
        if instruction_id not in settlements_by_instruction:
            mismatches.append(
                {
                    "instruction_id": instruction_id,
                    "mismatch_type": "missing_provider",
                    "provider_reference": None,
                }
            )

    for instruction_id in duplicate_provider:
        mismatches.append(
            {
                "instruction_id": instruction_id,
                "mismatch_type": "duplicate_provider_event",
                "provider_reference": settlements_by_instruction[instruction_id].get("provider_reference"),
            }
        )

    for mismatch in mismatches:
        if mismatch["mismatch_type"] not in MISMATCH_TYPES:
            raise PayoutRequestError(500, "internal_error", "unknown mismatch type generated")

    run = repository.save_reconciliation_run(
        {
            "organization_id": organization_id,
            "provider": provider,
            "run_started_at": started.isoformat(),
            "run_finished_at": datetime.now(timezone.utc).isoformat(),
            "run_status": "matched" if not mismatches else "mismatched",
            "matched_count": len(matched_entries),
            "mismatched_count": len(mismatches),
            "missing_internal_count": len(
                [m for m in mismatches if m["mismatch_type"] == "missing_internal"]
            ),
            "missing_provider_count": len(
                [m for m in mismatches if m["mismatch_type"] == "missing_provider"]
            ),
            "result_payload": {
                "matched_entries": matched_entries,
                "mismatches": mismatches,
            },
        }
    )
    return run


def get_reconciliation_run_persisted(
    *, run_id: str, organization_id: str, repository: Stage3Repository
) -> tuple[int, dict]:
    run = repository.get_reconciliation_run(run_id)
    if not run:
        raise PayoutRequestError(404, "not_found", "reconciliation run not found")
    if run["organization_id"] != organization_id:
        raise PayoutRequestError(403, "forbidden", "reconciliation run belongs to another organization")
    return 200, run
