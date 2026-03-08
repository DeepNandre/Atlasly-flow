from datetime import datetime, timezone
import unittest

from scripts.stage3.payout_api import AuthContext
from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.payout_api import PayoutStore
from scripts.stage3.payout_api import create_payout_instruction
from scripts.stage3.payout_api import transition_instruction_state


class Stage3Slice3PayoutApiTests(unittest.TestCase):
    def setUp(self):
        self.store = PayoutStore.empty()
        self.now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
        self.auth_admin = AuthContext(
            organization_id="3550f393-cf47-46e9-b146-19d6fbe7e910",
            requester_role="admin",
        )
        self.milestone = {
            "id": "941f2df0-69a8-4868-a892-d3f908e96ce4",
            "organization_id": "3550f393-cf47-46e9-b146-19d6fbe7e910",
            "project_id": "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35",
            "permit_id": "f199bac0-85c9-4ca7-9586-c2f3309bc39a",
            "milestone_state": "payout_eligible",
        }

    def test_payout_eligible_creates_instruction_and_event(self):
        status, instruction = create_payout_instruction(
            milestone=self.milestone,
            amount=2500.50,
            currency="USD",
            beneficiary_id="db4f6205-17af-4f17-8e8f-5107af6f2f16",
            provider="provider_sandbox",
            idempotency_key="idem_001",
            trace_id="trc_001",
            step_up_authenticated=True,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status, 201)
        self.assertEqual(instruction["instruction_state"], "created")
        self.assertEqual(len(self.store.outbox_events), 1)
        event = self.store.outbox_events[0]
        self.assertEqual(event["event_type"], "payout.instruction_created")
        self.assertEqual(event["event_version"], 1)
        self.assertEqual(event["aggregate_type"], "payout_instruction")

    def test_idempotency_replay_returns_same_instruction(self):
        first_status, first = create_payout_instruction(
            milestone=self.milestone,
            amount=100,
            currency="USD",
            beneficiary_id="f271938e-b6ee-4e3d-9f59-6905b082ec6f",
            provider="provider_sandbox",
            idempotency_key="idem_replay",
            trace_id="trc_002",
            step_up_authenticated=True,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )
        second_status, second = create_payout_instruction(
            milestone=self.milestone,
            amount=100,
            currency="USD",
            beneficiary_id="f271938e-b6ee-4e3d-9f59-6905b082ec6f",
            provider="provider_sandbox",
            idempotency_key="idem_replay",
            trace_id="trc_003",
            step_up_authenticated=True,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertEqual(first["instruction_id"], second["instruction_id"])
        self.assertEqual(len(self.store.outbox_events), 1)

    def test_invalid_milestone_state_returns_conflict(self):
        bad = dict(self.milestone)
        bad["milestone_state"] = "verified"
        with self.assertRaises(PayoutRequestError) as ctx:
            create_payout_instruction(
                milestone=bad,
                amount=100,
                currency="USD",
                beneficiary_id="9c2f0059-950e-45ab-b474-d9583b1a5f2c",
                provider="provider_sandbox",
                idempotency_key="idem_invalid_state",
                trace_id="trc_004",
                step_up_authenticated=True,
                auth_context=self.auth_admin,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(len(self.store.outbox_events), 0)

    def test_role_forbidden(self):
        with self.assertRaises(PayoutRequestError) as ctx:
            create_payout_instruction(
                milestone=self.milestone,
                amount=100,
                currency="USD",
                beneficiary_id="707b5f2f-03ce-45e9-ab2d-44f53b936e74",
                provider="provider_sandbox",
                idempotency_key="idem_role",
                trace_id="trc_005",
                step_up_authenticated=True,
                auth_context=AuthContext(
                    organization_id=self.auth_admin.organization_id,
                    requester_role="pm",
                ),
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_step_up_required(self):
        with self.assertRaises(PayoutRequestError) as ctx:
            create_payout_instruction(
                milestone=self.milestone,
                amount=100,
                currency="USD",
                beneficiary_id="6477bb9c-a76a-4258-8f44-c9aff1d1fdd9",
                provider="provider_sandbox",
                idempotency_key="idem_no_stepup",
                trace_id="trc_006",
                step_up_authenticated=False,
                auth_context=self.auth_admin,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 401)

    def test_invalid_currency(self):
        with self.assertRaises(PayoutRequestError) as ctx:
            create_payout_instruction(
                milestone=self.milestone,
                amount=100,
                currency="usd",
                beneficiary_id="d117eca6-c5fa-4f44-b0c8-f5f1687fa26f",
                provider="provider_sandbox",
                idempotency_key="idem_currency",
                trace_id="trc_007",
                step_up_authenticated=True,
                auth_context=self.auth_admin,
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)

    def test_transition_failure_states_and_invalid_transition(self):
        _, instruction = create_payout_instruction(
            milestone=self.milestone,
            amount=100,
            currency="USD",
            beneficiary_id="878f6535-a07d-4a44-b90a-93997ff65598",
            provider="provider_sandbox",
            idempotency_key="idem_transitions",
            trace_id="trc_008",
            step_up_authenticated=True,
            auth_context=self.auth_admin,
            store=self.store,
            now=self.now,
        )

        updated = transition_instruction_state(
            instruction_id=instruction["instruction_id"],
            new_state="failed_transient",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(updated["instruction_state"], "failed_transient")

        updated = transition_instruction_state(
            instruction_id=instruction["instruction_id"],
            new_state="submitted",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(updated["instruction_state"], "submitted")

        updated = transition_instruction_state(
            instruction_id=instruction["instruction_id"],
            new_state="failed_terminal",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(updated["instruction_state"], "failed_terminal")

        with self.assertRaises(PayoutRequestError) as ctx:
            transition_instruction_state(
                instruction_id=instruction["instruction_id"],
                new_state="submitted",
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
