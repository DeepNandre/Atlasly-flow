from datetime import datetime, timezone
import unittest

from scripts.stage3.finance_api import create_reconciliation_run_persisted
from scripts.stage3.finance_api import get_reconciliation_run_persisted
from scripts.stage3.finance_api import record_financial_event_persisted
from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import create_payout_instruction_persisted
from scripts.stage3.preflight_api import get_preflight_risk_persisted
from scripts.stage3.repositories import Stage3PersistenceStore
from scripts.stage3.repositories import Stage3Repository


class Stage3Slice5PersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 16, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.repo = Stage3Repository(Stage3PersistenceStore.empty())
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.project_record = {
            "organization_id": self.org_id,
            "created_at": datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
            "permit_id": "f199bac0-85c9-4ca7-9586-c2f3309bc39a",
        }
        self.milestone = {
            "id": "941f2df0-69a8-4868-a892-d3f908e96ce4",
            "organization_id": self.org_id,
            "project_id": self.project_id,
            "permit_id": self.project_record["permit_id"],
            "milestone_state": "payout_eligible",
        }

    def test_preflight_score_persists(self):
        status, payload = get_preflight_risk_persisted(
            self.project_id,
            {
                "permit_type": "commercial_ti",
                "ahj_id": "ca.san_jose.building",
            },
            auth_context=self.auth,
            project_record=self.project_record,
            repository=self.repo,
            server_now=self.now,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(self.repo._store.preflight_scores), 1)
        score = list(self.repo._store.preflight_scores.values())[0]
        self.assertEqual(score["project_id"], payload["project_id"])
        self.assertEqual(score["permit_type"], payload["permit_type"])

    def test_payout_idempotency_persists_single_instruction_and_event(self):
        first_status, first = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=1550.0,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key="idem_store_001",
            trace_id="trc_store_001",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )
        second_status, second = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=1550.0,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key="idem_store_001",
            trace_id="trc_store_002",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertEqual(first["instruction_id"], second["instruction_id"])
        self.assertEqual(len(self.repo._store.payout_instructions), 1)
        self.assertEqual(len(self.repo._store.outbox_events), 1)
        outbox = list(self.repo._store.outbox_events.values())[0]
        self.assertEqual(outbox["event_type"], "payout.instruction_created")
        self.assertEqual(outbox["event_version"], 1)

    def test_reconciliation_traceability_with_persisted_records(self):
        _, instruction = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=2300.0,
            currency="USD",
            beneficiary_id="08f2fd29-4a06-4fd6-a1ec-f262ef4a7e9e",
            provider="provider_sandbox",
            idempotency_key="idem_store_003",
            trace_id="trc_store_003",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        record_financial_event_persisted(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            milestone_id=instruction["milestone_id"],
            event_type="instruction_submitted",
            amount=instruction["amount"],
            currency="USD",
            trace_id="trc_ledger_store_1",
            source_service="payout-service",
            payload={"provider_reference": "settl_store_1"},
            occurred_at=self.now,
            repository=self.repo,
        )

        run = create_reconciliation_run_persisted(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[
                {
                    "instruction_id": instruction["instruction_id"],
                    "amount": 2300.0,
                    "currency": "USD",
                    "provider_reference": "settl_store_1",
                }
            ],
            repository=self.repo,
            run_started_at=self.now,
        )
        self.assertEqual(run["run_status"], "matched")

        status, fetched = get_reconciliation_run_persisted(
            run_id=run["id"],
            organization_id=self.org_id,
            repository=self.repo,
        )
        self.assertEqual(status, 200)
        self.assertEqual(fetched["matched_count"], 1)
        self.assertEqual(
            fetched["result_payload"]["matched_entries"][0]["instruction_id"],
            instruction["instruction_id"],
        )


if __name__ == "__main__":
    unittest.main()
