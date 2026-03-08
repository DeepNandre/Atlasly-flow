from datetime import datetime, timezone
import unittest

from scripts.stage3.finance_api import FinanceStore
from scripts.stage3.finance_api import create_reconciliation_run
from scripts.stage3.finance_api import get_reconciliation_run
from scripts.stage3.finance_api import record_financial_event
from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.payout_api import PayoutStore
from scripts.stage3.payout_api import create_payout_instruction


class Stage3Slice4ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 3, 14, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.milestone = {
            "id": "941f2df0-69a8-4868-a892-d3f908e96ce4",
            "organization_id": self.org_id,
            "project_id": "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            "permit_id": "f199bac0-85c9-4ca7-9586-c2f3309bc39a",
            "milestone_state": "payout_eligible",
        }
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.payout_store = PayoutStore.empty()
        self.finance_store = FinanceStore.empty()

    def _create_instruction(self, idempotency_key: str, amount: float = 1200.0):
        _, instruction = create_payout_instruction(
            milestone=self.milestone,
            amount=amount,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key=idempotency_key,
            trace_id=f"trc_{idempotency_key}",
            step_up_authenticated=True,
            auth_context=self.auth,
            store=self.payout_store,
            now=self.now,
        )
        return instruction

    def test_e2e_payout_to_reconciliation_match(self):
        instruction = self._create_instruction("idem_match")

        record_financial_event(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            milestone_id=instruction["milestone_id"],
            event_type="instruction_submitted",
            amount=instruction["amount"],
            currency="USD",
            trace_id="trc_ledger_1",
            source_service="payout-service",
            payload={"provider_reference": "settl_001"},
            occurred_at=self.now,
            store=self.finance_store,
        )

        run = create_reconciliation_run(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[
                {
                    "instruction_id": instruction["instruction_id"],
                    "amount": instruction["amount"],
                    "currency": "USD",
                    "provider_reference": "settl_001",
                }
            ],
            store=self.finance_store,
            run_started_at=self.now,
        )

        self.assertEqual(run["run_status"], "matched")
        self.assertEqual(run["matched_count"], 1)
        self.assertEqual(run["mismatched_count"], 0)

        status, fetched = get_reconciliation_run(
            run_id=run["id"],
            organization_id=self.org_id,
            store=self.finance_store,
        )
        self.assertEqual(status, 200)
        self.assertEqual(fetched["id"], run["id"])
        self.assertEqual(fetched["result_payload"]["matched_entries"][0]["instruction_id"], instruction["instruction_id"])

    def test_amount_mismatch_classification(self):
        instruction = self._create_instruction("idem_amount_mismatch", amount=500)
        record_financial_event(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            milestone_id=instruction["milestone_id"],
            event_type="instruction_submitted",
            amount=500,
            currency="USD",
            trace_id="trc_ledger_2",
            source_service="payout-service",
            payload={"provider_reference": "settl_002"},
            occurred_at=self.now,
            store=self.finance_store,
        )

        run = create_reconciliation_run(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[
                {
                    "instruction_id": instruction["instruction_id"],
                    "amount": 700,
                    "currency": "USD",
                    "provider_reference": "settl_002",
                }
            ],
            store=self.finance_store,
            run_started_at=self.now,
        )
        self.assertEqual(run["run_status"], "mismatched")
        mismatch_types = {m["mismatch_type"] for m in run["result_payload"]["mismatches"]}
        self.assertIn("amount_mismatch", mismatch_types)

    def test_missing_provider_classification(self):
        instruction = self._create_instruction("idem_missing_provider", amount=100)
        record_financial_event(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            milestone_id=instruction["milestone_id"],
            event_type="instruction_submitted",
            amount=100,
            currency="USD",
            trace_id="trc_ledger_3",
            source_service="payout-service",
            payload={"provider_reference": "settl_003"},
            occurred_at=self.now,
            store=self.finance_store,
        )

        run = create_reconciliation_run(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[],
            store=self.finance_store,
            run_started_at=self.now,
        )
        mismatch_types = {m["mismatch_type"] for m in run["result_payload"]["mismatches"]}
        self.assertIn("missing_provider", mismatch_types)

    def test_missing_internal_and_duplicate_provider_event_classification(self):
        external_instruction_id = "aa111111-1111-1111-1111-111111111111"
        run = create_reconciliation_run(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[
                {
                    "instruction_id": external_instruction_id,
                    "amount": 200,
                    "currency": "USD",
                    "provider_reference": "settl_dup_1",
                },
                {
                    "instruction_id": external_instruction_id,
                    "amount": 200,
                    "currency": "USD",
                    "provider_reference": "settl_dup_2",
                },
            ],
            store=self.finance_store,
            run_started_at=self.now,
        )
        mismatch_types = {m["mismatch_type"] for m in run["result_payload"]["mismatches"]}
        self.assertIn("missing_internal", mismatch_types)
        self.assertIn("duplicate_provider_event", mismatch_types)

    def test_get_reconciliation_run_tenant_isolation(self):
        run = create_reconciliation_run(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[],
            store=self.finance_store,
            run_started_at=self.now,
        )
        with self.assertRaises(PayoutRequestError) as ctx:
            get_reconciliation_run(
                run_id=run["id"],
                organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                store=self.finance_store,
            )
        self.assertEqual(ctx.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
