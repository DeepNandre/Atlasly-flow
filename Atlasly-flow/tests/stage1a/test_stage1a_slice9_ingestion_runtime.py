from __future__ import annotations

from datetime import datetime, timezone
import base64
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1a.comment_extraction_service import Stage1ARequestError
from scripts.stage1a.ingestion_runtime import enqueue_upload_job
from scripts.stage1a.ingestion_runtime import IngestionStore
from scripts.stage1a.ingestion_runtime import process_next_upload_job
from scripts.stage1a.ingestion_runtime import process_upload_job


class Stage1ASlice9IngestionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 3, 22, 0, tzinfo=timezone.utc)
        self.org_id = "3550f393-cf47-46e9-b146-19d6fbe7e910"
        self.project_id = "7a6dc13a-34a6-4fce-9f01-8d97f36d3d35"
        self.store = IngestionStore.empty()

    @staticmethod
    def _as_base64(text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    def test_enqueue_and_process_upload_job(self) -> None:
        upload_status, upload = enqueue_upload_job(
            organization_id=self.org_id,
            project_id=self.project_id,
            filename="comments.txt",
            mime_type="text/plain",
            document_base64=self._as_base64(
                "Revise panel schedule per NEC 408.4\nProvide duct sizing report per IMC 603.2"
            ),
            idempotency_key="upload-idem-001",
            trace_id="trace-upload-001",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(upload_status, 202)
        self.assertIn("job_id", upload)

        process_status, processed = process_upload_job(
            organization_id=self.org_id,
            job_id=upload["job_id"],
            store=self.store,
            now=self.now,
        )
        self.assertEqual(process_status, 200)
        self.assertEqual(processed["status"], "completed")
        self.assertGreaterEqual(processed["page_count"], 1)
        self.assertIn(1, processed["page_text_by_number"])
        self.assertIn(1, processed["ocr_quality_by_page"])

        replay_status, replay = process_upload_job(
            organization_id=self.org_id,
            job_id=upload["job_id"],
            store=self.store,
            now=self.now,
        )
        self.assertEqual(replay_status, 200)
        self.assertTrue(replay["idempotent_replay"])

    def test_enqueue_idempotent_replay(self) -> None:
        status1, payload1 = enqueue_upload_job(
            organization_id=self.org_id,
            project_id=self.project_id,
            filename="comments.txt",
            mime_type="text/plain",
            document_base64=self._as_base64("Line one"),
            idempotency_key="upload-idem-002",
            trace_id="trace-upload-002",
            store=self.store,
            now=self.now,
        )
        status2, payload2 = enqueue_upload_job(
            organization_id=self.org_id,
            project_id=self.project_id,
            filename="comments.txt",
            mime_type="text/plain",
            document_base64=self._as_base64("Line one"),
            idempotency_key="upload-idem-002",
            trace_id="trace-upload-003",
            store=self.store,
            now=self.now,
        )
        self.assertEqual(status1, 202)
        self.assertEqual(status2, 200)
        self.assertEqual(payload1["job_id"], payload2["job_id"])
        self.assertTrue(payload2["idempotent_replay"])

    def test_process_next_job_idle_and_tenant_boundary(self) -> None:
        idle_status, idle = process_next_upload_job(
            organization_id=self.org_id,
            store=self.store,
            now=self.now,
        )
        self.assertEqual(idle_status, 200)
        self.assertEqual(idle["status"], "idle")

        _, upload = enqueue_upload_job(
            organization_id=self.org_id,
            project_id=self.project_id,
            filename="comments.txt",
            mime_type="text/plain",
            document_base64=self._as_base64("Line one"),
            idempotency_key="upload-idem-003",
            trace_id="trace-upload-004",
            store=self.store,
            now=self.now,
        )
        with self.assertRaises(Stage1ARequestError) as ctx:
            process_upload_job(
                organization_id="bf72b0e8-0d5d-4f14-b3f3-b0f2f551f1ef",
                job_id=upload["job_id"],
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 403)

    def test_invalid_base64_rejected(self) -> None:
        with self.assertRaises(Stage1ARequestError) as ctx:
            enqueue_upload_job(
                organization_id=self.org_id,
                project_id=self.project_id,
                filename="comments.pdf",
                mime_type="application/pdf",
                document_base64="%%%invalid%%%",
                idempotency_key="upload-idem-004",
                trace_id="trace-upload-005",
                store=self.store,
                now=self.now,
            )
        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "validation_error")


if __name__ == "__main__":
    unittest.main()
