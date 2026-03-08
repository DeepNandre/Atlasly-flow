from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import io
import pathlib
import re
import shutil
import subprocess
import tempfile
import uuid

from scripts.stage1a.comment_extraction_service import Stage1ARequestError


MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass
class IngestionStore:
    jobs_by_id: dict[str, dict]
    queue_job_ids: list[str]
    job_by_org_idempotency: dict[tuple[str, str], str]

    @classmethod
    def empty(cls) -> "IngestionStore":
        return cls(jobs_by_id={}, queue_job_ids=[], job_by_org_idempotency={})


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _decode_base64_payload(raw: str) -> bytes:
    payload = str(raw or "").strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    if not payload:
        raise Stage1ARequestError(422, "validation_error", "document_base64 is required")
    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise Stage1ARequestError(422, "validation_error", "document_base64 must be valid base64") from exc


def _line_quality_score(line: str) -> float:
    if not line:
        return 0.0
    printable = sum(1 for ch in line if ch.isprintable())
    alpha_num = sum(1 for ch in line if ch.isalnum())
    printable_ratio = printable / max(1, len(line))
    alpha_ratio = alpha_num / max(1, len(line))
    return round(min(1.0, 0.65 * printable_ratio + 0.35 * alpha_ratio), 3)


def _normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\x0c", "\n---PAGE_BREAK---\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _extract_page_text(*, filename: str, mime_type: str, document_bytes: bytes) -> tuple[dict[int, str], dict[int, float]]:
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        pdf_page_text = _extract_pdf_page_text(document_bytes=document_bytes)
        if pdf_page_text:
            pdf_quality = {
                page_no: round(min(0.99, max(0.55, _line_quality_score(text))), 3)
                for page_no, text in pdf_page_text.items()
            }
            return pdf_page_text, pdf_quality

    is_text_like = (
        mime_type.startswith("text/")
        or filename.lower().endswith(".txt")
        or filename.lower().endswith(".md")
        or mime_type in {"application/json", "application/xml"}
    )

    if is_text_like:
        raw_text = document_bytes.decode("utf-8", errors="replace")
    else:
        # OCR placeholder path for scanned/PDF-like blobs in demo runtime.
        raw_text = document_bytes.decode("latin-1", errors="replace")

    normalized = _normalize_text(raw_text)
    if not normalized:
        raise Stage1ARequestError(422, "validation_error", "document content is empty after OCR normalization")

    page_text_by_number: dict[int, str] = {}
    ocr_quality_by_page: dict[int, float] = {}

    chunks = [chunk.strip() for chunk in normalized.split("---PAGE_BREAK---")]
    page_no = 1
    for chunk in chunks:
        if not chunk:
            continue
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        if not lines:
            continue
        merged = " ".join(lines)
        page_text_by_number[page_no] = merged
        line_scores = [_line_quality_score(line) for line in lines]
        ocr_quality_by_page[page_no] = round(sum(line_scores) / max(1, len(line_scores)), 3)
        page_no += 1

    if not page_text_by_number:
        raise Stage1ARequestError(422, "validation_error", "document content produced no OCR pages")

    return page_text_by_number, ocr_quality_by_page


def _extract_pdf_page_text(*, document_bytes: bytes) -> dict[int, str]:
    page_text = _extract_pdf_page_text_with_pypdf(document_bytes=document_bytes)
    if page_text:
        return page_text
    page_text = _extract_pdf_page_text_with_pdftotext(document_bytes=document_bytes)
    if page_text:
        return page_text
    return {}


def _extract_pdf_page_text_with_pypdf(*, document_bytes: bytes) -> dict[int, str]:
    try:
        import pypdf  # type: ignore
    except Exception:  # noqa: BLE001
        return {}

    try:
        reader = pypdf.PdfReader(io.BytesIO(document_bytes))
    except Exception:  # noqa: BLE001
        return {}

    page_text_by_number: dict[int, str] = {}
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = str(page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001
            text = ""
        text = _normalize_text(text)
        if text:
            page_text_by_number[idx] = text
    return page_text_by_number


def _extract_pdf_page_text_with_pdftotext(*, document_bytes: bytes) -> dict[int, str]:
    if shutil.which("pdftotext") is None:
        return {}

    with tempfile.TemporaryDirectory(prefix="atlasly-pdf-") as tmp:
        pdf_path = pathlib.Path(tmp) / "input.pdf"
        txt_path = pathlib.Path(tmp) / "output.txt"
        pdf_path.write_bytes(document_bytes)
        try:
            subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception:  # noqa: BLE001
            return {}
        if not txt_path.exists():
            return {}
        text = _normalize_text(txt_path.read_text(encoding="utf-8", errors="replace"))
        if not text:
            return {}
        chunks = [chunk.strip() for chunk in text.split("\x0c") if chunk.strip()]
        if not chunks:
            chunks = [text]
        return {idx: chunk for idx, chunk in enumerate(chunks, start=1)}


def enqueue_upload_job(
    *,
    organization_id: str,
    project_id: str,
    filename: str,
    mime_type: str,
    document_base64: str,
    idempotency_key: str,
    trace_id: str,
    store: IngestionStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    if not organization_id.strip() or not project_id.strip():
        raise Stage1ARequestError(422, "validation_error", "organization_id and project_id are required")
    if not filename.strip():
        raise Stage1ARequestError(422, "validation_error", "filename is required")
    if not idempotency_key.strip():
        raise Stage1ARequestError(400, "invalid_request", "Idempotency-Key is required")

    ts = now or datetime.now(timezone.utc)
    key = (organization_id, idempotency_key)
    existing_id = store.job_by_org_idempotency.get(key)
    if existing_id:
        existing = store.jobs_by_id[existing_id]
        return 200, {
            "job_id": existing["job_id"],
            "status": existing["status"],
            "idempotent_replay": True,
        }

    document_bytes = _decode_base64_payload(document_base64)
    if len(document_bytes) > MAX_UPLOAD_BYTES:
        raise Stage1ARequestError(413, "payload_too_large", f"file exceeds {MAX_UPLOAD_BYTES} bytes limit")

    job_id = str(uuid.uuid4())
    row = {
        "job_id": job_id,
        "organization_id": organization_id,
        "project_id": project_id,
        "filename": filename.strip(),
        "mime_type": str(mime_type or "application/octet-stream").strip().lower(),
        "status": "queued",
        "trace_id": trace_id,
        "sha256": hashlib.sha256(document_bytes).hexdigest(),
        "size_bytes": len(document_bytes),
        "queued_at": _iso(ts),
        "updated_at": _iso(ts),
        "document_bytes": document_bytes,
        "page_text_by_number": None,
        "ocr_quality_by_page": None,
        "error_code": None,
        "error_message": None,
    }

    store.jobs_by_id[job_id] = row
    store.queue_job_ids.append(job_id)
    store.job_by_org_idempotency[key] = job_id
    return 202, {
        "job_id": job_id,
        "status": row["status"],
        "queued_at": row["queued_at"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
    }


def process_upload_job(
    *,
    organization_id: str,
    job_id: str,
    store: IngestionStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    row = store.jobs_by_id.get(job_id)
    if not row:
        raise Stage1ARequestError(404, "not_found", "ingestion job not found")
    if row["organization_id"] != organization_id:
        raise Stage1ARequestError(403, "forbidden", "ingestion job belongs to another organization")

    if row["status"] == "completed":
        return 200, {
            "job_id": row["job_id"],
            "status": row["status"],
            "page_count": len(row["page_text_by_number"] or {}),
            "idempotent_replay": True,
            "page_text_by_number": dict(row["page_text_by_number"] or {}),
            "ocr_quality_by_page": dict(row["ocr_quality_by_page"] or {}),
        }

    if row["status"] == "failed":
        raise Stage1ARequestError(409, "invalid_state", "ingestion job is failed and cannot be reprocessed")

    ts = now or datetime.now(timezone.utc)
    row["status"] = "processing"
    row["updated_at"] = _iso(ts)

    try:
        page_text_by_number, ocr_quality_by_page = _extract_page_text(
            filename=row["filename"],
            mime_type=row["mime_type"],
            document_bytes=row["document_bytes"],
        )
    except Stage1ARequestError as exc:
        row["status"] = "failed"
        row["error_code"] = exc.code
        row["error_message"] = exc.message
        row["updated_at"] = _iso(datetime.now(timezone.utc))
        raise

    row["page_text_by_number"] = page_text_by_number
    row["ocr_quality_by_page"] = ocr_quality_by_page
    row["status"] = "completed"
    row["updated_at"] = _iso(datetime.now(timezone.utc))

    if job_id in store.queue_job_ids:
        store.queue_job_ids = [queued for queued in store.queue_job_ids if queued != job_id]

    return 200, {
        "job_id": row["job_id"],
        "status": row["status"],
        "page_count": len(page_text_by_number),
        "page_text_by_number": dict(page_text_by_number),
        "ocr_quality_by_page": dict(ocr_quality_by_page),
    }


def process_next_upload_job(
    *,
    organization_id: str,
    store: IngestionStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    for queued_id in list(store.queue_job_ids):
        row = store.jobs_by_id.get(queued_id)
        if not row:
            continue
        if row["organization_id"] != organization_id:
            continue
        return process_upload_job(organization_id=organization_id, job_id=queued_id, store=store, now=now)

    return 200, {"status": "idle", "processed": False}
