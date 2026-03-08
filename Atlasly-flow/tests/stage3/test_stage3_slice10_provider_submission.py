from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage3.payout_api import PayoutRequestError
from scripts.stage3.provider_submission import submit_provider_instruction


class Stage3Slice10ProviderSubmissionTests(unittest.TestCase):
    def test_provider_sandbox_submission_returns_reference(self):
        result = submit_provider_instruction(
            instruction={
                "instruction_id": "ins-1",
                "milestone_id": "ms-1",
                "amount": 100.0,
                "currency": "USD",
                "provider": "provider_sandbox",
            },
            stripe_secret_key=None,
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["provider_event_type"], "instruction.submitted")
        self.assertTrue(str(result["provider_reference"]).startswith("sandbox-"))

    def test_stripe_submission_requires_secret(self):
        with self.assertRaises(PayoutRequestError) as ctx:
            submit_provider_instruction(
                instruction={
                    "instruction_id": "ins-2",
                    "milestone_id": "ms-2",
                    "amount": 100.0,
                    "currency": "USD",
                    "provider": "stripe_sandbox",
                },
                stripe_secret_key="",
            )
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(ctx.exception.code, "provider_unavailable")


if __name__ == "__main__":
    unittest.main()
