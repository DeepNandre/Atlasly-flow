from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pathlib
import statistics
import sys
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage0.foundation_api import get_project_timeline_api
from scripts.stage0.foundation_api import patch_permits_api
from scripts.stage0.foundation_api import patch_tasks_api
from scripts.stage0.foundation_api import post_org_user_invite_api
from scripts.stage0.foundation_api import post_orgs_api
from scripts.stage0.foundation_api import post_project_documents_api
from scripts.stage0.foundation_api import post_project_permits_api
from scripts.stage0.foundation_api import post_project_tasks_api
from scripts.stage0.foundation_api import post_projects_api
from scripts.stage0.foundation_service import AuthContext
from scripts.stage0.foundation_service import Stage0RequestError
from scripts.stage0.foundation_service import Stage0Store
from scripts.stage0.foundation_service import mark_document_ocr_completed
from scripts.stage0.foundation_service import verify_audit_chain


class Stage0FoundationRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
        self.store = Stage0Store.empty()

    def _create_org(self, *, slug: str, owner_email: str) -> tuple[dict, AuthContext]:
        status, payload = post_orgs_api(
            request_body={
                "name": f"{slug} Inc",
                "slug": slug,
                "owner_user": {
                    "email": owner_email,
                    "full_name": "Owner User",
                },
            },
            headers={"Idempotency-Key": f"idem-{slug}", "X-Request-Id": f"req-{slug}"},
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status, 201)
        org_id = payload["organization"]["id"]
        owner_membership = payload["owner_membership"]["id"]
        owner_user_id = self.store.memberships_by_id[owner_membership]["user_id"]
        return payload, AuthContext(organization_id=org_id, user_id=owner_user_id, requester_role="owner")

    def test_post_orgs_idempotent_replay_and_conflict(self):
        status1, payload1 = post_orgs_api(
            request_body={
                "name": "Atlas GC",
                "slug": "atlas-gc",
                "owner_user": {"email": "owner@atlasgc.com", "full_name": "Owner Name"},
            },
            headers={"Idempotency-Key": "idem-org-1", "X-Request-Id": "req-org-1"},
            store=self.store,
            now=self.now,
        )
        status2, payload2 = post_orgs_api(
            request_body={
                "name": "Atlas GC",
                "slug": "atlas-gc",
                "owner_user": {"email": "owner@atlasgc.com", "full_name": "Owner Name"},
            },
            headers={"Idempotency-Key": "idem-org-1", "X-Request-Id": "req-org-2"},
            store=self.store,
            now=self.now,
        )
        status3, payload3 = post_orgs_api(
            request_body={
                "name": "Atlas GC Renamed",
                "slug": "atlas-gc",
                "owner_user": {"email": "owner@atlasgc.com", "full_name": "Owner Name"},
            },
            headers={"Idempotency-Key": "idem-org-1", "X-Request-Id": "req-org-3"},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status1, 201)
        self.assertEqual(status2, 200)
        self.assertTrue(payload2["idempotency_replayed"])
        self.assertEqual(payload1["organization"]["id"], payload2["organization"]["id"])
        self.assertEqual(status3, 409)
        self.assertEqual(payload3["error"]["code"], "conflict")

    def test_membership_partial_uniqueness_org_and_workspace(self):
        org_payload, owner_auth = self._create_org(slug="partial-unique", owner_email="owner1@example.com")
        org_id = org_payload["organization"]["id"]
        workspace_id = org_payload["default_workspace"]["id"]

        status1, payload1 = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "pm@example.com",
                "full_name": "PM",
                "role": "pm",
                "workspace_id": None,
            },
            headers={"X-Request-Id": "req-invite-1"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        status2, payload2 = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "pm@example.com",
                "full_name": "PM",
                "role": "pm",
                "workspace_id": None,
            },
            headers={"X-Request-Id": "req-invite-2"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        status3, payload3 = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "pm@example.com",
                "full_name": "PM",
                "role": "pm",
                "workspace_id": workspace_id,
            },
            headers={"X-Request-Id": "req-invite-3"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        status4, payload4 = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "pm@example.com",
                "full_name": "PM",
                "role": "pm",
                "workspace_id": workspace_id,
            },
            headers={"X-Request-Id": "req-invite-4"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(status1, 201)
        self.assertEqual(status2, 409)
        self.assertEqual(status2, 409)
        self.assertEqual(status3, 201)
        self.assertEqual(status4, 409)
        self.assertEqual(payload1["membership"]["workspace_id"], None)
        self.assertEqual(payload3["membership"]["workspace_id"], workspace_id)
        self.assertEqual(payload2["error"]["code"], "conflict")
        self.assertEqual(payload4["error"]["code"], "conflict")

    def test_stage0_lifecycle_and_required_domain_events(self):
        org_payload, owner_auth = self._create_org(slug="lifecycle-org", owner_email="owner.lifecycle@example.com")
        org_id = org_payload["organization"]["id"]
        workspace_id = org_payload["default_workspace"]["id"]

        status_pm, payload_pm = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "pm.lifecycle@example.com",
                "full_name": "PM Lifecycle",
                "role": "pm",
                "workspace_id": None,
            },
            headers={"X-Request-Id": "req-pm"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_pm, 201)
        pm_user_id = payload_pm["membership"]["user_id"]
        pm_auth = AuthContext(organization_id=org_id, user_id=pm_user_id, requester_role="pm")

        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_id,
                "workspace_id": workspace_id,
                "name": "Warehouse Retrofit",
                "project_code": "WR-001",
                "ahj_profile": {"name": "City of Austin", "jurisdiction_type": "city", "region": "TX"},
            },
            headers={"Idempotency-Key": "idem-project-1", "X-Request-Id": "req-project-1"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)
        project_id = payload_project["project"]["id"]

        status_permit_create, payload_permit_create = post_project_permits_api(
            project_id=project_id,
            request_body={"permit_type": "building"},
            headers={"X-Request-Id": "req-permit-create"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_permit_create, 201)
        permit_id = payload_permit_create["permit"]["id"]

        status_patch_1, _ = patch_permits_api(
            permit_id=permit_id,
            request_body={"status": "submitted", "source": "user_action"},
            headers={"X-Request-Id": "req-permit-1"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        status_patch_2, _ = patch_permits_api(
            permit_id=permit_id,
            request_body={"status": "in_review", "source": "user_action"},
            headers={"X-Request-Id": "req-permit-2"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_patch_1, 200)
        self.assertEqual(status_patch_2, 200)

        status_task, payload_task = post_project_tasks_api(
            project_id=project_id,
            request_body={
                "title": "Address egress comments",
                "discipline": "architectural",
                "permit_id": permit_id,
                "assignee_user_id": pm_user_id,
                "due_date": "2026-03-20",
                "priority": 2,
            },
            headers={"Idempotency-Key": "idem-task-1", "X-Request-Id": "req-task-1"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_task, 201)
        task_id = payload_task["task"]["id"]
        self.assertEqual(len(self.store.notification_jobs_by_id), 2)

        status_patch_task, payload_patch_task = patch_tasks_api(
            task_id=task_id,
            request_body={"status": "in_progress"},
            headers={"If-Match": "1", "X-Request-Id": "req-task-2"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_patch_task, 200)
        self.assertEqual(payload_patch_task["task"]["version"], 2)

        status_doc, payload_doc = post_project_documents_api(
            project_id=project_id,
            request_body={
                "title": "Architectural Plans",
                "category": "plans",
                "file_name": "plans-v1.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 2048,
                "checksum_sha256": "sha-doc-v1",
                "storage_upload": {"bucket": "permits-docs", "key": "org/project/doc/v1/plans-v1.pdf"},
            },
            headers={"Idempotency-Key": "idem-doc-1", "X-Request-Id": "req-doc-1"},
            auth_context=pm_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_doc, 201)
        doc_id = payload_doc["document"]["id"]
        self.assertEqual(payload_doc["version"]["version_no"], 1)

        ocr_row = mark_document_ocr_completed(
            document_id=doc_id,
            version=1,
            ocr_status="completed",
            page_count=12,
            error_code=None,
            organization_id=org_id,
            store=self.store,
            now=self.now,
            trace_id="trace-ocr",
        )
        self.assertEqual(ocr_row["ocr_status"], "completed")

        status_timeline, payload_timeline = get_project_timeline_api(
            project_id=project_id,
            query_params={"limit": 100},
            auth_context=pm_auth,
            store=self.store,
        )
        self.assertEqual(status_timeline, 200)
        self.assertGreaterEqual(len(payload_timeline["items"]), 6)
        self.assertGreaterEqual(len(self.store.audit_events), 7)

        emitted_types = {event["event_type"] for event in self.store.domain_events}
        required = {
            "document.uploaded",
            "document.ocr_completed",
            "task.created",
            "task.assigned",
            "permit.status_changed",
        }
        self.assertTrue(required.issubset(emitted_types))

    def test_subcontractor_can_update_assigned_task_status_only(self):
        org_payload, owner_auth = self._create_org(slug="subcontractor-org", owner_email="owner.sub@example.com")
        org_id = org_payload["organization"]["id"]
        workspace_id = org_payload["default_workspace"]["id"]

        status_sub, payload_sub = post_org_user_invite_api(
            org_id=org_id,
            request_body={
                "email": "sub1@example.com",
                "full_name": "Sub One",
                "role": "subcontractor",
                "workspace_id": None,
            },
            headers={"X-Request-Id": "req-sub"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_sub, 201)
        sub_user_id = payload_sub["membership"]["user_id"]
        sub_auth = AuthContext(organization_id=org_id, user_id=sub_user_id, requester_role="subcontractor")

        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_id,
                "workspace_id": workspace_id,
                "name": "Sub Project",
                "project_code": "SUB-001",
            },
            headers={"Idempotency-Key": "idem-sub-project", "X-Request-Id": "req-sub-project"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)
        project_id = payload_project["project"]["id"]

        status_task, payload_task = post_project_tasks_api(
            project_id=project_id,
            request_body={
                "title": "Assigned to sub",
                "assignee_user_id": sub_user_id,
                "priority": 3,
            },
            headers={"Idempotency-Key": "idem-sub-task", "X-Request-Id": "req-sub-task"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_task, 201)
        task_id = payload_task["task"]["id"]

        status_patch_ok, payload_patch_ok = patch_tasks_api(
            task_id=task_id,
            request_body={"status": "in_progress"},
            headers={"If-Match": "1", "X-Request-Id": "req-sub-patch-1"},
            auth_context=sub_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_patch_ok, 200)
        self.assertEqual(payload_patch_ok["task"]["status"], "in_progress")

        status_patch_forbidden, payload_patch_forbidden = patch_tasks_api(
            task_id=task_id,
            request_body={"assignee_user_id": owner_auth.user_id},
            headers={"If-Match": "2", "X-Request-Id": "req-sub-patch-2"},
            auth_context=sub_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_patch_forbidden, 403)
        self.assertEqual(payload_patch_forbidden["error"]["code"], "forbidden")

    def test_tenant_isolation_blocks_cross_org_access(self):
        org1, owner1 = self._create_org(slug="org-one", owner_email="owner1@iso.com")
        org2, owner2 = self._create_org(slug="org-two", owner_email="owner2@iso.com")

        status_p1, payload_p1 = post_projects_api(
            request_body={
                "organization_id": org1["organization"]["id"],
                "workspace_id": org1["default_workspace"]["id"],
                "name": "Org1 Project",
                "project_code": "ORG1-001",
            },
            headers={"Idempotency-Key": "idem-o1-p1", "X-Request-Id": "req-o1-p1"},
            auth_context=owner1,
            store=self.store,
            now=self.now,
        )
        status_p2, payload_p2 = post_projects_api(
            request_body={
                "organization_id": org2["organization"]["id"],
                "workspace_id": org2["default_workspace"]["id"],
                "name": "Org2 Project",
                "project_code": "ORG2-001",
            },
            headers={"Idempotency-Key": "idem-o2-p1", "X-Request-Id": "req-o2-p1"},
            auth_context=owner2,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_p1, 201)
        self.assertEqual(status_p2, 201)

        status_tl, payload_tl = get_project_timeline_api(
            project_id=payload_p2["project"]["id"],
            query_params={},
            auth_context=owner1,
            store=self.store,
        )
        self.assertEqual(status_tl, 404)
        self.assertEqual(payload_tl["error"]["code"], "not_found")

        status_invite, payload_invite = post_org_user_invite_api(
            org_id=org2["organization"]["id"],
            request_body={
                "email": "another@example.com",
                "full_name": "Another",
                "role": "pm",
                "workspace_id": None,
            },
            headers={"X-Request-Id": "req-cross-org-invite"},
            auth_context=owner1,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_invite, 403)
        self.assertEqual(payload_invite["error"]["code"], "forbidden")

    def test_invalid_permit_transition_is_rejected(self):
        org_payload, owner_auth = self._create_org(slug="permit-transition", owner_email="owner.permit@example.com")
        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_payload["organization"]["id"],
                "workspace_id": org_payload["default_workspace"]["id"],
                "name": "Permit Project",
            },
            headers={"Idempotency-Key": "idem-permit-project", "X-Request-Id": "req-permit-project"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)
        project_id = payload_project["project"]["id"]

        status_create, payload_create = post_project_permits_api(
            project_id=project_id,
            request_body={"permit_type": "building"},
            headers={"X-Request-Id": "req-permit-create-2"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_create, 201)
        permit_id = payload_create["permit"]["id"]

        status_invalid, payload_invalid = patch_permits_api(
            permit_id=permit_id,
            request_body={"status": "approved", "source": "user_action"},
            headers={"X-Request-Id": "req-permit-invalid"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_invalid, 422)
        self.assertEqual(payload_invalid["error"]["code"], "validation_failed")

    def test_document_ocr_terminal_transition_conflict(self):
        org_payload, owner_auth = self._create_org(slug="ocr-guard-org", owner_email="owner.ocr@example.com")
        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_payload["organization"]["id"],
                "workspace_id": org_payload["default_workspace"]["id"],
                "name": "OCR Guard Project",
            },
            headers={"Idempotency-Key": "idem-ocr-project", "X-Request-Id": "req-ocr-project"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)
        project_id = payload_project["project"]["id"]

        status_doc, payload_doc = post_project_documents_api(
            project_id=project_id,
            request_body={
                "title": "Permit comments",
                "category": "comments",
                "file_name": "comments.pdf",
                "mime_type": "application/pdf",
                "file_size_bytes": 2048,
                "checksum_sha256": "sha-ocr-doc-v1",
                "storage_upload": {"bucket": "permits-docs", "key": "ocr/guard/comments-v1.pdf"},
            },
            headers={"Idempotency-Key": "idem-ocr-doc", "X-Request-Id": "req-ocr-doc"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_doc, 201)
        doc_id = payload_doc["document"]["id"]

        completed = mark_document_ocr_completed(
            document_id=doc_id,
            version=1,
            ocr_status="completed",
            page_count=10,
            error_code=None,
            organization_id=owner_auth.organization_id,
            store=self.store,
            now=self.now,
            trace_id="trace-ocr-complete",
        )
        self.assertEqual(completed["ocr_status"], "completed")

        with self.assertRaises(Stage0RequestError) as conflict:
            mark_document_ocr_completed(
                document_id=doc_id,
                version=1,
                ocr_status="failed",
                page_count=None,
                error_code="post_complete_failure",
                organization_id=owner_auth.organization_id,
                store=self.store,
                now=self.now,
                trace_id="trace-ocr-invalid-transition",
            )
        self.assertEqual(conflict.exception.status, 409)

    def test_verify_audit_chain_detects_tamper(self):
        org_payload, owner_auth = self._create_org(slug="audit-chain-org", owner_email="owner.audit@example.com")
        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_payload["organization"]["id"],
                "workspace_id": org_payload["default_workspace"]["id"],
                "name": "Audit Project",
            },
            headers={"Idempotency-Key": "idem-audit-project", "X-Request-Id": "req-audit-project"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)

        status, failing_id = verify_audit_chain(
            organization_id=owner_auth.organization_id,
            store=self.store,
        )
        self.assertTrue(status)
        self.assertIsNone(failing_id)

        self.store.audit_events[-1]["payload"] = {"tampered": True}
        status_after, failing_after = verify_audit_chain(
            organization_id=owner_auth.organization_id,
            store=self.store,
        )
        self.assertFalse(status_after)
        self.assertEqual(failing_after, self.store.audit_events[-1]["id"])

    def test_timeline_query_p95_under_300ms_for_10k_events(self):
        org_payload, owner_auth = self._create_org(slug="latency-org", owner_email="owner.latency@example.com")
        status_project, payload_project = post_projects_api(
            request_body={
                "organization_id": org_payload["organization"]["id"],
                "workspace_id": org_payload["default_workspace"]["id"],
                "name": "Timeline Load Project",
                "project_code": "TL-001",
            },
            headers={"Idempotency-Key": "idem-lat-project", "X-Request-Id": "req-lat-project"},
            auth_context=owner_auth,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status_project, 201)
        project_id = payload_project["project"]["id"]

        base = self.now - timedelta(minutes=10000)
        for idx in range(10000):
            self.store.audit_events.append(
                {
                    "id": str(uuid.uuid4()),
                    "organization_id": owner_auth.organization_id,
                    "project_id": project_id,
                    "actor_user_id": owner_auth.user_id,
                    "action": "task.updated",
                    "entity_type": "task",
                    "entity_id": str(uuid.uuid4()),
                    "occurred_at": (base + timedelta(seconds=idx)).isoformat(),
                    "request_id": f"req-{idx}",
                    "trace_id": f"trace-{idx}",
                    "payload": {"i": idx},
                    "prev_hash": None,
                    "event_hash": f"h{idx}",
                    "immutable": True,
                }
            )

        samples = []
        for _ in range(100):
            started = time.perf_counter()
            status, payload = get_project_timeline_api(
                project_id=project_id,
                query_params={"limit": 50},
                auth_context=owner_auth,
                store=self.store,
            )
            elapsed = time.perf_counter() - started
            self.assertEqual(status, 200)
            self.assertEqual(len(payload["items"]), 50)
            samples.append(elapsed)

        p95 = statistics.quantiles(samples, n=20)[-1]
        self.assertLessEqual(p95, 0.300, f"expected p95 <= 0.300s, got {p95:.6f}s")


if __name__ == "__main__":
    unittest.main()
