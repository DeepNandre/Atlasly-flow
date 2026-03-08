from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pathlib
import sys
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.webapp_server import DemoAppState


class ControlTowerPerformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = DemoAppState()
        self.state.bootstrap()
        self.assertIsNotNone(self.state.ids)

    def tearDown(self) -> None:
        self.state.stage2_repo.close()
        self.state.stage3_store.repository.close()

    def test_portfolio_and_activity_response_time_with_synthetic_load(self):
        assert self.state.ids is not None
        org_id = self.state.ids.organization_id
        workspace_id = self.state.ids.workspace_id
        base_time = datetime(2026, 3, 3, 0, 0, tzinfo=timezone.utc)

        for idx in range(180):
            project_id = str(uuid.uuid4())
            permit_id = str(uuid.uuid4())
            created_at = (base_time + timedelta(seconds=idx)).isoformat()
            self.state.stage0_store.projects_by_id[project_id] = {
                "id": project_id,
                "organization_id": org_id,
                "workspace_id": workspace_id,
                "ahj_profile_id": None,
                "name": f"Synthetic Project {idx}",
                "project_code": f"SYN-{idx:04d}",
                "address": {"city": "San Jose", "state": "CA"},
                "metadata": {},
                "created_by": self.state.ids.owner_user_id,
                "created_at": created_at,
                "updated_at": created_at,
            }
            self.state.stage0_store.permits_by_id[permit_id] = {
                "id": permit_id,
                "organization_id": org_id,
                "project_id": project_id,
                "permit_type": "commercial_ti",
                "status": "draft",
                "submitted_at": None,
                "issued_at": None,
                "expired_at": None,
                "metadata": {},
                "created_by": self.state.ids.owner_user_id,
                "created_at": created_at,
                "updated_at": created_at,
            }

            task_id = str(uuid.uuid4())
            ticket_store = self.state.stage1b_repo.load_ticket_store()
            ticket_store.tasks_by_id[task_id] = {
                "id": task_id,
                "organization_id": org_id,
                "project_id": project_id,
                "source_extraction_id": str(uuid.uuid4()),
                "title": "Synthetic task",
                "discipline": "electrical",
                "status": "todo",
                "auto_assigned": True,
                "assignment_confidence": 0.91,
                "assignee_user_id": self.state.ids.pm_user_id,
                "first_assigned_at": created_at,
                "created_at": created_at,
                "updated_at": created_at,
            }
            self.state.stage1b_repo.save_ticket_store(ticket_store)

            self.state.stage0_store.audit_events.append(
                {
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "project_id": project_id,
                    "actor_user_id": self.state.ids.owner_user_id,
                    "action": "task.updated",
                    "entity_type": "task",
                    "entity_id": task_id,
                    "occurred_at": created_at,
                    "request_id": f"req-syn-{idx}",
                    "trace_id": f"trc-syn-{idx}",
                    "payload": {"i": idx},
                    "prev_hash": None,
                    "event_hash": f"syn-hash-{idx}",
                    "immutable": True,
                }
            )

        portfolio_start = time.perf_counter()
        portfolio = self.state.portfolio()
        portfolio_elapsed = time.perf_counter() - portfolio_start

        activity_start = time.perf_counter()
        activity = self.state.activity_feed(limit=200)
        activity_elapsed = time.perf_counter() - activity_start

        self.assertGreaterEqual(len(portfolio["projects"]), 181)
        self.assertGreaterEqual(len(activity["events"]), 150)
        self.assertLessEqual(portfolio_elapsed, 1.2, f"portfolio exceeded threshold: {portfolio_elapsed:.4f}s")
        self.assertLessEqual(activity_elapsed, 0.9, f"activity exceeded threshold: {activity_elapsed:.4f}s")


if __name__ == "__main__":
    unittest.main()
