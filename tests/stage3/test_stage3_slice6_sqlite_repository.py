from datetime import datetime, timezone
import sqlite3
import unittest

from scripts.stage3.finance_api import create_reconciliation_run_persisted
from scripts.stage3.finance_api import get_reconciliation_run_persisted
from scripts.stage3.finance_api import record_financial_event_persisted
from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.payout_api import create_payout_instruction_persisted
from scripts.stage3.payout_api import transition_instruction_state_persisted
from scripts.stage3.sqlite_repository import Stage3SQLiteRepository


class Stage3Slice6SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = Stage3SQLiteRepository()
        self.now = datetime(2026, 3, 3, 18, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.auth = AuthContext(organization_id=self.org_id, requester_role="admin")
        self.milestone = {
            "id": "941f2df0-69a8-4868-a892-d3f908e96ce4",
            "organization_id": self.org_id,
            "project_id": "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            "permit_id": "f199bac0-85c9-4ca7-9586-c2f3309bc39a",
            "milestone_state": "payout_eligible",
        }

    def tearDown(self):
        self.repo.close()

    def test_persisted_idempotency_with_sqlite_repo(self):
        first_status, first = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=999.99,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_1",
            trace_id="trc_sqlite_1",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )
        second_status, second = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=999.99,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_1",
            trace_id="trc_sqlite_2",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertEqual(first["instruction_id"], second["instruction_id"])
        self.assertEqual(self.repo.count_rows("payout_instructions"), 1)
        self.assertEqual(self.repo.count_rows("stage3_event_outbox"), 1)

    def test_atomic_rollback_when_outbox_insert_fails(self):
        self.repo.insert_outbox_event(
            {
                "event_id": "aa111111-1111-1111-1111-111111111111",
                "organization_id": self.org_id,
                "event_type": "payout.instruction_created",
                "event_version": 1,
                "aggregate_type": "payout_instruction",
                "aggregate_id": "seed",
                "idempotency_key": "idem_conflict",
                "trace_id": "trc_seed",
                "payload": {"seed": True},
                "occurred_at": self.now.isoformat(),
                "produced_by": "payout-service",
            }
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_instruction_with_outbox(
                organization_id=self.org_id,
                idempotency_key="idem_conflict",
                instruction={
                    "instruction_id": "bb222222-2222-2222-2222-222222222222",
                    "organization_id": self.org_id,
                    "milestone_id": self.milestone["id"],
                    "permit_id": self.milestone["permit_id"],
                    "project_id": self.milestone["project_id"],
                    "beneficiary_id": "user-x",
                    "amount": 100.00,
                    "currency": "USD",
                    "provider": "provider_sandbox",
                    "instruction_state": "created",
                    "idempotency_key": "idem_conflict",
                    "created_at": self.now.isoformat(),
                    "updated_at": self.now.isoformat(),
                },
                event={
                    "event_id": "cc333333-3333-3333-3333-333333333333",
                    "organization_id": self.org_id,
                    "event_type": "payout.instruction_created",
                    "event_version": 1,
                    "aggregate_type": "payout_instruction",
                    "aggregate_id": "bb222222-2222-2222-2222-222222222222",
                    "idempotency_key": "idem_conflict",
                    "trace_id": "trc_conflict",
                    "payload": {"instruction_id": "bb222222-2222-2222-2222-222222222222"},
                    "occurred_at": self.now.isoformat(),
                    "produced_by": "payout-service",
                },
            )

        self.assertEqual(self.repo.count_rows("payout_instructions"), 0)
        self.assertEqual(self.repo.count_rows("stage3_event_outbox"), 1)

    def test_reconciliation_persist_and_read_with_sqlite_repo(self):
        _, instruction = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=1500.0,
            currency="USD",
            beneficiary_id="beneficiary-1",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_3",
            trace_id="trc_sqlite_3",
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
            amount=1500.0,
            currency="USD",
            trace_id="trc_ledger_sqlite",
            source_service="payout-service",
            payload={"provider_reference": "settl_sql_1"},
            occurred_at=self.now,
            repository=self.repo,
        )

        run = create_reconciliation_run_persisted(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[
                {
                    "instruction_id": instruction["instruction_id"],
                    "amount": 1500.0,
                    "currency": "USD",
                    "provider_reference": "settl_sql_1",
                }
            ],
            repository=self.repo,
            run_started_at=self.now,
        )

        status, fetched = get_reconciliation_run_persisted(
            run_id=run["id"],
            organization_id=self.org_id,
            repository=self.repo,
        )
        self.assertEqual(status, 200)
        self.assertEqual(fetched["run_status"], "matched")
        self.assertEqual(fetched["matched_count"], 1)

    def test_same_org_transition_persisted_allows_mutation(self):
        _, instruction = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=200.0,
            currency="USD",
            beneficiary_id="beneficiary-2",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_transition_ok",
            trace_id="trc_sqlite_transition_ok",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        updated = transition_instruction_state_persisted(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            new_state="submitted",
            repository=self.repo,
            now=self.now,
        )
        self.assertEqual(updated["instruction_state"], "submitted")

    def test_cross_org_transition_persisted_blocked_without_mutation(self):
        _, instruction = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=210.0,
            currency="USD",
            beneficiary_id="beneficiary-3",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_transition_block",
            trace_id="trc_sqlite_transition_block",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        with self.assertRaises(PayoutRequestError) as ctx:
            transition_instruction_state_persisted(
                organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                instruction_id=instruction["instruction_id"],
                new_state="submitted",
                repository=self.repo,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 404)

        same_org_record = self.repo.get_payout_instruction(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
        )
        self.assertIsNotNone(same_org_record)
        self.assertEqual(same_org_record["instruction_state"], "created")

    def test_listing_helpers_return_recent_finance_rows(self):
        _, instruction = create_payout_instruction_persisted(
            milestone=self.milestone,
            amount=88.0,
            currency="USD",
            beneficiary_id="beneficiary-list",
            provider="provider_sandbox",
            idempotency_key="idem_sqlite_list_helper",
            trace_id="trc_sqlite_list_helper",
            step_up_authenticated=True,
            auth_context=self.auth,
            repository=self.repo,
            now=self.now,
        )

        transition_instruction_state_persisted(
            organization_id=self.org_id,
            instruction_id=instruction["instruction_id"],
            new_state="submitted",
            repository=self.repo,
            now=self.now,
        )

        run = create_reconciliation_run_persisted(
            organization_id=self.org_id,
            provider="provider_sandbox",
            provider_settlements=[],
            repository=self.repo,
            run_started_at=self.now,
        )

        listed_instructions = self.repo.list_payout_instructions_by_org(organization_id=self.org_id, limit=10)
        self.assertGreaterEqual(len(listed_instructions), 1)
        self.assertEqual(listed_instructions[0]["organization_id"], self.org_id)

        listed_runs = self.repo.list_reconciliation_runs_by_org(organization_id=self.org_id, limit=10)
        self.assertGreaterEqual(len(listed_runs), 1)
        self.assertEqual(listed_runs[0]["id"], run["id"])


if __name__ == "__main__":
    unittest.main()
