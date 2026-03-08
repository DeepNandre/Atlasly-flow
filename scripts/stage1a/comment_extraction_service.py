from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import re
import uuid

DISCIPLINES = {
    "structural",
    "electrical",
    "plumbing",
    "mechanical",
    "fire",
    "zoning",
    "civil",
    "architectural",
    "energy",
    "accessibility",
    "other",
}

SEVERITIES = {"critical", "major", "minor", "info"}

EXTRACTION_STATUSES = {
    "auto_accepted",
    "needs_review",
    "reviewed_corrected",
    "approved_snapshot",
}

LETTER_STATES = {
    "ingest_received",
    "ocr_precheck",
    "ocr_processing",
    "extracting_comments",
    "normalizing_validating",
    "review_queueing",
    "human_review",
    "approval_snapshot",
    "completed",
    "failed_extraction",
}

WRITE_ROLES = {"owner", "admin", "pm", "reviewer"}
APPROVE_ROLES = {"owner", "admin", "pm", "reviewer"}

CODE_FAMILY_BY_PATTERN = {
    "IBC": re.compile(r"\bIBC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "IRC": re.compile(r"\bIRC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "IECC": re.compile(r"\bIECC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "IFC": re.compile(r"\bIFC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "NEC": re.compile(r"\bNEC\s*\d+(?:\.\d+)*(?:\([A-Za-z0-9]+\))*\b", re.IGNORECASE),
    "IPC": re.compile(r"\bIPC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "IMC": re.compile(r"\bIMC\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
    "NFPA": re.compile(r"\bNFPA\s*\d+(?:\.\d+)*\b", re.IGNORECASE),
}

DISCIPLINE_KEYWORDS = {
    "structural": {"beam", "load", "shear", "foundation", "structural"},
    "electrical": {"electrical", "panel", "circuit", "conductor", "nec"},
    "plumbing": {"plumbing", "fixture", "waste", "vent", "ipc"},
    "mechanical": {"mechanical", "duct", "hvac", "airflow", "imc"},
    "fire": {"fire", "egress", "alarm", "sprinkler", "ifc"},
    "zoning": {"zoning", "setback", "lot", "height", "coverage"},
    "civil": {"grading", "drainage", "civil", "storm", "site"},
    "architectural": {"architectural", "door", "window", "plan", "sheet"},
    "energy": {"energy", "iecc", "insulation", "efficiency", "u-factor"},
    "accessibility": {"accessibility", "ada", "clearance", "accessible", "ramp"},
}

ACTION_VERBS = {
    "revise",
    "provide",
    "update",
    "submit",
    "add",
    "clarify",
    "correct",
    "install",
    "replace",
}


class Stage1ARequestError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    organization_id: str
    requester_role: str
    user_id: str | None = None


@dataclass
class Stage1AStore:
    letters_by_id: dict[str, dict]
    letter_id_by_org_idempotency: dict[tuple[str, str], str]
    extractions_by_id: dict[str, dict]
    extraction_ids_by_letter: dict[str, list[str]]
    extraction_reviews_by_id: dict[str, dict]
    extraction_feedback_by_id: dict[str, dict]
    approval_snapshots_by_letter: dict[str, dict]
    emitted_event_keys: set[tuple[str, str, int]]
    outbox_events: list[dict]

    @classmethod
    def empty(cls) -> "Stage1AStore":
        return cls({}, {}, {}, {}, {}, {}, {}, set(), [])


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _require_role(auth_context: AuthContext, allowed: set[str]) -> None:
    if auth_context.requester_role not in allowed:
        raise Stage1ARequestError(403, "forbidden", "role not permitted for Stage 1A operation")


def _event_envelope(
    *,
    event_type: str,
    aggregate_id: str,
    organization_id: str,
    idempotency_key: str,
    trace_id: str,
    payload: dict,
    occurred_at: datetime,
    produced_by: str,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "organization_id": organization_id,
        "aggregate_type": "comment_letter",
        "aggregate_id": aggregate_id,
        "occurred_at": _iso(occurred_at),
        "produced_by": produced_by,
        "idempotency_key": idempotency_key,
        "trace_id": trace_id,
        "payload": payload,
    }


def _emit_event_once(
    *,
    letter_id: str,
    event_type: str,
    payload: dict,
    store: Stage1AStore,
    organization_id: str,
    trace_id: str,
    occurred_at: datetime,
    produced_by: str,
) -> bool:
    key = (letter_id, event_type, 1)
    if key in store.emitted_event_keys:
        return False
    store.emitted_event_keys.add(key)
    store.outbox_events.append(
        _event_envelope(
            event_type=event_type,
            aggregate_id=letter_id,
            organization_id=organization_id,
            idempotency_key=f"{letter_id}:{event_type}:v1",
            trace_id=trace_id,
            payload=payload,
            occurred_at=occurred_at,
            produced_by=produced_by,
        )
    )
    return True


def _transition_allowed(from_state: str, to_state: str) -> bool:
    if from_state == to_state:
        return True
    allowed = {
        "ingest_received": {"ocr_precheck", "failed_extraction"},
        "ocr_precheck": {"ocr_processing", "extracting_comments", "failed_extraction"},
        "ocr_processing": {"extracting_comments", "failed_extraction"},
        "extracting_comments": {"normalizing_validating", "failed_extraction"},
        "normalizing_validating": {"review_queueing", "failed_extraction"},
        "review_queueing": {"human_review", "approval_snapshot", "failed_extraction"},
        "human_review": {"approval_snapshot", "failed_extraction"},
        "approval_snapshot": {"completed", "failed_extraction"},
        "completed": set(),
        "failed_extraction": set(),
    }
    return to_state in allowed.get(from_state, set())


def _set_letter_state(letter: dict, to_state: str) -> None:
    cur = str(letter["status"])
    if cur not in LETTER_STATES or to_state not in LETTER_STATES:
        raise Stage1ARequestError(500, "internal_error", "invalid Stage 1A state")
    if not _transition_allowed(cur, to_state):
        raise Stage1ARequestError(409, "invalid_state", f"invalid state transition {cur} -> {to_state}")
    letter["status"] = to_state


def _safe_div(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _infer_code_family(code_ref: str) -> str:
    if not code_ref.strip():
        return "UNKNOWN"
    for family, pattern in CODE_FAMILY_BY_PATTERN.items():
        if pattern.search(code_ref):
            return family
    return "UNKNOWN"


def _is_code_ref_valid(code_ref: str) -> bool:
    if not code_ref.strip():
        return True
    return _infer_code_family(code_ref) != "UNKNOWN"


def _keyword_alignment_factor(discipline: str, raw_text: str) -> float:
    if discipline == "other":
        return 0.85
    keywords = DISCIPLINE_KEYWORDS.get(discipline, set())
    if not keywords:
        return 0.85
    text = raw_text.lower()
    hit_count = sum(1 for kw in keywords if kw in text)
    if hit_count >= 2:
        return 1.0
    if hit_count == 1:
        return 0.9
    return 0.75


def _severity_rule_alignment(severity: str, raw_text: str) -> float:
    text = raw_text.lower()
    critical_markers = {"life safety", "immediate", "hazard", "danger"}
    soft_markers = {"note", "clarify", "information", "coordination"}
    has_critical = any(m in text for m in critical_markers)
    has_soft = any(m in text for m in soft_markers)
    if severity == "critical" and has_critical:
        return 1.0
    if severity == "info" and has_soft:
        return 1.0
    if severity == "critical" and not has_critical:
        return 0.8
    if severity == "info" and not has_soft:
        return 0.8
    return 0.92


def _action_verb_score(requested_action: str) -> float:
    words = requested_action.strip().lower().split()
    if not words:
        return 0.0
    return 1.0 if words[0] in ACTION_VERBS else 0.82


def _completeness_score(requested_action: str) -> float:
    word_count = len([w for w in requested_action.strip().split() if w])
    return min(1.0, _safe_div(word_count, 12.0))


def _text_overlap_floor(raw_text: str, page_text: str) -> float:
    raw_tokens = {t for t in re.findall(r"[a-z0-9]+", raw_text.lower())}
    page_tokens = {t for t in re.findall(r"[a-z0-9]+", page_text.lower())}
    if not raw_tokens:
        return 0.0
    return _safe_div(len(raw_tokens & page_tokens), len(raw_tokens))


def _build_comment_id(page_number: int, raw_text: str) -> str:
    norm = re.sub(r"\s+", " ", raw_text.strip().lower())
    digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]
    return f"cmt_{page_number}_{digest}"


def _compute_confidence(
    *,
    raw_text: str,
    discipline: str,
    severity: str,
    requested_action: str,
    code_reference: str,
    citation_quote: str,
    page_text: str,
    ocr_low_quality: bool,
    model_prob_discipline: float,
    model_prob_severity: float,
    model_prob_code_reference: float,
) -> tuple[dict[str, float], float, list[str], bool, bool]:
    exact_citation_match = bool(citation_quote and citation_quote in page_text)
    citation_similarity = _similarity(citation_quote, page_text)

    text_match_score = 1.0 if raw_text and raw_text in page_text else max(_similarity(raw_text, page_text), citation_similarity)
    c_raw_text = max(0.0, min(1.0, text_match_score))

    c_discipline = max(0.0, min(1.0, model_prob_discipline * _keyword_alignment_factor(discipline, raw_text)))
    c_severity = max(0.0, min(1.0, model_prob_severity * _severity_rule_alignment(severity, raw_text)))

    c_requested_action = max(
        0.0,
        min(1.0, _action_verb_score(requested_action) * _completeness_score(requested_action)),
    )

    valid_code_format = _is_code_ref_valid(code_reference)
    format_factor = 1.0 if valid_code_format else 0.5
    source_presence = 1.0 if (code_reference and (code_reference in raw_text or code_reference in citation_quote)) else 0.75
    c_code_reference = max(0.0, min(1.0, model_prob_code_reference * format_factor * source_presence))

    c_citation = 1.0 if exact_citation_match else max(0.0, min(1.0, citation_similarity))

    c_record = (
        0.22 * c_raw_text
        + 0.18 * c_discipline
        + 0.12 * c_severity
        + 0.20 * c_requested_action
        + 0.18 * c_code_reference
        + 0.10 * c_citation
    )

    hard_violation = False
    soft_violation = False
    flags: list[str] = []

    if not citation_quote:
        c_record -= 0.20
        hard_violation = True
    if code_reference.strip() and not valid_code_format:
        c_record -= 0.15
        hard_violation = True
        flags.append("code_ref_unverified")
    if ocr_low_quality:
        c_record -= 0.10
        flags.append("ocr_low_quality_page")

    overlap = _text_overlap_floor(raw_text, page_text)
    if overlap < 0.55:
        hard_violation = True
    if discipline == "other" and c_discipline < 0.85:
        soft_violation = True
        flags.append("discipline_low_signal")
    if len(requested_action.split()) < 12:
        soft_violation = True
    if not exact_citation_match and ocr_low_quality:
        flags.append("citation_span_fuzzy_match")

    c_record = max(0.0, min(1.0, c_record))

    fields = {
        "raw_text": round(c_raw_text, 3),
        "discipline": round(c_discipline, 3),
        "severity": round(c_severity, 3),
        "requested_action": round(c_requested_action, 3),
        "code_reference": round(c_code_reference, 3),
        "citation": round(c_citation, 3),
    }

    return fields, round(c_record, 3), flags, hard_violation, soft_violation


def _determine_status(record_confidence: float, hard_violation: bool, soft_violation: bool) -> str:
    if hard_violation:
        return "needs_review"
    if record_confidence >= 0.92 and not soft_violation:
        return "auto_accepted"
    return "needs_review"


def create_comment_letter(
    *,
    project_id: str,
    document_id: str,
    idempotency_key: str,
    trace_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
    source_filename: str | None = None,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, WRITE_ROLES)
    if not idempotency_key.strip():
        raise Stage1ARequestError(400, "invalid_request", "Idempotency-Key is required")

    key = (auth_context.organization_id, idempotency_key)
    existing_id = store.letter_id_by_org_idempotency.get(key)
    if existing_id:
        letter = store.letters_by_id[existing_id]
        return 200, {
            "letter_id": existing_id,
            "status": letter["status"],
            "idempotent_replay": True,
        }

    ts = now or datetime.now(timezone.utc)
    letter_id = str(uuid.uuid4())
    letter = {
        "letter_id": letter_id,
        "organization_id": auth_context.organization_id,
        "project_id": project_id,
        "document_id": document_id,
        "created_by": auth_context.user_id,
        "status": "ingest_received",
        "source_filename": source_filename,
        "idempotency_key": idempotency_key,
        "started_at": _iso(ts),
        "created_at": _iso(ts),
        "updated_at": _iso(ts),
        "approved_at": None,
        "completed_at": None,
    }
    store.letters_by_id[letter_id] = letter
    store.letter_id_by_org_idempotency[key] = letter_id
    store.extraction_ids_by_letter.setdefault(letter_id, [])

    _emit_event_once(
        letter_id=letter_id,
        event_type="comment_letter.parsing_started",
        payload={
            "letter_id": letter_id,
            "document_id": document_id,
            "started_at": _iso(ts),
        },
        store=store,
        organization_id=auth_context.organization_id,
        trace_id=trace_id,
        occurred_at=ts,
        produced_by="stage1a-parser-worker",
    )

    return 202, {
        "letter_id": letter_id,
        "status": "ingest_received",
    }


def process_extraction_candidates(
    *,
    letter_id: str,
    candidates: list[dict[str, object]],
    page_text_by_number: dict[int, str],
    ocr_quality_by_page: dict[int, float] | None,
    trace_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, WRITE_ROLES)
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    ts = now or datetime.now(timezone.utc)

    if letter["status"] == "ingest_received":
        _set_letter_state(letter, "ocr_precheck")
    if letter["status"] == "ocr_precheck":
        needs_ocr = any((ocr_quality_by_page or {}).get(pg, 1.0) < 0.85 for pg in page_text_by_number)
        _set_letter_state(letter, "ocr_processing" if needs_ocr else "extracting_comments")
    if letter["status"] == "ocr_processing":
        _set_letter_state(letter, "extracting_comments")
    if letter["status"] == "extracting_comments":
        _set_letter_state(letter, "normalizing_validating")

    if letter["status"] != "normalizing_validating":
        raise Stage1ARequestError(409, "invalid_state", "letter must be in normalizing_validating")

    existing_ids = list(store.extraction_ids_by_letter.get(letter_id, []))
    for extraction_id in existing_ids:
        store.extractions_by_id.pop(extraction_id, None)
    store.extraction_ids_by_letter[letter_id] = []

    processed: list[dict] = []

    for idx, candidate in enumerate(candidates):
        raw_text = str(candidate.get("raw_text") or "").strip()
        discipline = str(candidate.get("discipline") or "other").strip().lower()
        severity = str(candidate.get("severity") or "minor").strip().lower()
        requested_action = str(candidate.get("requested_action") or "").strip()
        code_reference = str(candidate.get("code_reference") or "").strip()
        page_number = int(candidate.get("page_number") or 0)
        citation_obj = candidate.get("citation") if isinstance(candidate.get("citation"), dict) else {}
        citation_quote = str(citation_obj.get("quote") or candidate.get("citation_quote") or "").strip()
        citation_char_start = int(citation_obj.get("char_start") or candidate.get("citation_char_start") or 0)
        citation_char_end = int(citation_obj.get("char_end") or candidate.get("citation_char_end") or max(1, citation_char_start + 1))

        if len(raw_text) < 20 or len(raw_text) > 4000:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] raw_text length invalid")
        if discipline not in DISCIPLINES:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] discipline invalid")
        if severity not in SEVERITIES:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] severity invalid")
        if len(requested_action) < 10 or len(requested_action) > 1000:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] requested_action length invalid")
        if page_number < 1:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] page_number invalid")

        page_text = page_text_by_number.get(page_number)
        if page_text is None:
            raise Stage1ARequestError(422, "validation_error", f"candidate[{idx}] page_number not found in source")

        ocr_quality = (ocr_quality_by_page or {}).get(page_number, 1.0)
        ocr_low_quality = ocr_quality < 0.80

        fields, record_confidence, flags, hard_violation, soft_violation = _compute_confidence(
            raw_text=raw_text,
            discipline=discipline,
            severity=severity,
            requested_action=requested_action,
            code_reference=code_reference,
            citation_quote=citation_quote,
            page_text=page_text,
            ocr_low_quality=ocr_low_quality,
            model_prob_discipline=float(candidate.get("model_prob_discipline", 0.9)),
            model_prob_severity=float(candidate.get("model_prob_severity", 0.9)),
            model_prob_code_reference=float(candidate.get("model_prob_code_reference", 0.9)),
        )

        status = _determine_status(record_confidence, hard_violation, soft_violation)
        code_family = _infer_code_family(code_reference)

        extraction_id = str(uuid.uuid4())
        comment_id = str(candidate.get("comment_id") or _build_comment_id(page_number, raw_text))
        extraction = {
            "id": extraction_id,
            "comment_id": comment_id,
            "letter_id": letter_id,
            "raw_text": raw_text,
            "discipline": discipline,
            "severity": severity,
            "requested_action": requested_action,
            "code_reference": code_reference,
            "code_reference_jurisdiction": str(candidate.get("code_reference_jurisdiction") or ""),
            "code_reference_family": code_family,
            "code_reference_valid_format": _is_code_ref_valid(code_reference),
            "page_number": page_number,
            "citation_quote": citation_quote,
            "citation_char_start": max(0, citation_char_start),
            "citation_char_end": max(citation_char_start + 1, citation_char_end),
            "confidence_fields": fields,
            "confidence": round(record_confidence, 3),
            "status": status,
            "normalization_flags": sorted(set(flags)),
            "created_at": _iso(ts),
            "updated_at": _iso(ts),
        }
        store.extractions_by_id[extraction_id] = extraction
        store.extraction_ids_by_letter.setdefault(letter_id, []).append(extraction_id)
        processed.append(extraction)

    # Duplicate detection pass.
    for i in range(len(processed)):
        for j in range(i + 1, len(processed)):
            left = processed[i]
            right = processed[j]
            if left["page_number"] != right["page_number"]:
                continue
            if _similarity(left["raw_text"], right["raw_text"]) > 0.95:
                if "possible_duplicate" not in left["normalization_flags"]:
                    left["normalization_flags"].append("possible_duplicate")
                    left["normalization_flags"] = sorted(set(left["normalization_flags"]))
                if "possible_duplicate" not in right["normalization_flags"]:
                    right["normalization_flags"].append("possible_duplicate")
                    right["normalization_flags"] = sorted(set(right["normalization_flags"]))
                left["status"] = "needs_review"
                right["status"] = "needs_review"

    _set_letter_state(letter, "review_queueing")
    letter["updated_at"] = _iso(ts)

    extraction_count = len(processed)
    avg_conf = round(
        sum(float(ex["confidence"]) for ex in processed) / extraction_count,
        3,
    ) if extraction_count else 0.0
    requires_review_count = sum(1 for ex in processed if ex["status"] == "needs_review")

    _emit_event_once(
        letter_id=letter_id,
        event_type="comment_letter.extraction_completed",
        payload={
            "letter_id": letter_id,
            "document_id": letter["document_id"],
            "extraction_count": extraction_count,
            "avg_confidence": avg_conf,
            "requires_review_count": requires_review_count,
            "completed_at": _iso(ts),
        },
        store=store,
        organization_id=auth_context.organization_id,
        trace_id=trace_id,
        occurred_at=ts,
        produced_by="stage1a-parser-worker",
    )

    return 200, {
        "letter_id": letter_id,
        "status": letter["status"],
        "extraction_count": extraction_count,
        "avg_confidence": avg_conf,
        "requires_review_count": requires_review_count,
    }


def get_comment_letter_status(*, letter_id: str, auth_context: AuthContext, store: Stage1AStore) -> tuple[int, dict]:
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    extraction_ids = store.extraction_ids_by_letter.get(letter_id, [])
    rows = [store.extractions_by_id[eid] for eid in extraction_ids]
    extraction_count = len(rows)
    avg_confidence = round(sum(float(row["confidence"]) for row in rows) / extraction_count, 3) if rows else 0.0
    requires_review_count = sum(1 for row in rows if row["status"] == "needs_review")

    return 200, {
        "letter_id": letter_id,
        "status": letter["status"],
        "extraction_count": extraction_count,
        "avg_confidence": avg_confidence,
        "requires_review_count": requires_review_count,
    }


def list_comment_extractions(*, letter_id: str, auth_context: AuthContext, store: Stage1AStore) -> tuple[int, dict]:
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    rows = [store.extractions_by_id[eid] for eid in store.extraction_ids_by_letter.get(letter_id, [])]
    rows.sort(key=lambda row: (int(row["page_number"]), row["comment_id"]))
    return 200, {
        "letter_id": letter_id,
        "extractions": rows,
    }


def review_extraction(
    *,
    letter_id: str,
    extraction_id: str,
    decision: str,
    correction_payload: dict[str, object] | None,
    rationale: str,
    auth_context: AuthContext,
    store: Stage1AStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, APPROVE_ROLES)
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    extraction = store.extractions_by_id.get(extraction_id)
    if not extraction or extraction["letter_id"] != letter_id:
        raise Stage1ARequestError(404, "not_found", "extraction not found")

    if decision not in {"accepted", "corrected", "rejected"}:
        raise Stage1ARequestError(422, "validation_error", "invalid review decision")

    ts = now or datetime.now(timezone.utc)

    if letter["status"] == "review_queueing":
        _set_letter_state(letter, "human_review")

    patch = correction_payload or {}
    if decision == "corrected" and patch:
        for key in (
            "raw_text",
            "discipline",
            "severity",
            "requested_action",
            "code_reference",
            "citation_quote",
        ):
            if key in patch and patch[key] is not None:
                extraction[key] = str(patch[key])
        extraction["updated_at"] = _iso(ts)

    extraction["status"] = "reviewed_corrected"

    review_id = str(uuid.uuid4())
    review = {
        "id": review_id,
        "letter_id": letter_id,
        "extraction_id": extraction_id,
        "reviewer_id": auth_context.user_id,
        "decision": decision,
        "correction_payload": patch,
        "rationale": rationale,
        "reviewed_at": _iso(ts),
    }
    store.extraction_reviews_by_id[review_id] = review

    feedback_id = str(uuid.uuid4())
    feedback = {
        "id": feedback_id,
        "letter_id": letter_id,
        "extraction_id": extraction_id,
        "source": "reviewer",
        "feedback_type": "action_fix" if decision == "corrected" else "other",
        "payload": {
            "decision": decision,
            "rationale": rationale,
            "correction_payload": patch,
        },
        "created_by": auth_context.user_id,
        "created_at": _iso(ts),
    }
    store.extraction_feedback_by_id[feedback_id] = feedback

    return 200, {
        "review_id": review_id,
        "feedback_id": feedback_id,
        "extraction_id": extraction_id,
        "status": extraction["status"],
    }


def approve_comment_letter(
    *,
    letter_id: str,
    trace_id: str,
    auth_context: AuthContext,
    store: Stage1AStore,
    now: datetime | None = None,
) -> tuple[int, dict]:
    _require_role(auth_context, APPROVE_ROLES)
    if not auth_context.user_id:
        raise Stage1ARequestError(401, "unauthorized", "authenticated user identity is required")
    try:
        uuid.UUID(str(auth_context.user_id))
    except Exception as exc:  # noqa: BLE001
        raise Stage1ARequestError(401, "unauthorized", "authenticated user identity is invalid") from exc
    approved_by = str(auth_context.user_id)

    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    existing_snapshot = store.approval_snapshots_by_letter.get(letter_id)
    if existing_snapshot:
        return 200, {
            "letter_id": letter_id,
            "approved_by": existing_snapshot["approved_by"],
            "approved_at": existing_snapshot["approved_at"],
            "snapshot_id": existing_snapshot["snapshot_id"],
            "idempotent_replay": True,
        }

    rows = [store.extractions_by_id[eid] for eid in store.extraction_ids_by_letter.get(letter_id, [])]
    if any(row["status"] == "needs_review" for row in rows):
        raise Stage1ARequestError(409, "invalid_state", "cannot approve with pending needs_review extractions")

    ts = now or datetime.now(timezone.utc)

    if letter["status"] in {"review_queueing", "human_review"}:
        _set_letter_state(letter, "approval_snapshot")

    for row in rows:
        if row["status"] in {"auto_accepted", "reviewed_corrected"}:
            row["status"] = "approved_snapshot"
            row["updated_at"] = _iso(ts)

    snapshot_id = str(uuid.uuid4())
    snapshot = {
        "snapshot_id": snapshot_id,
        "letter_id": letter_id,
        "approved_by": approved_by,
        "approved_at": _iso(ts),
        "extraction_count": len(rows),
        "snapshot_payload": [dict(row) for row in rows],
    }
    store.approval_snapshots_by_letter[letter_id] = snapshot

    _emit_event_once(
        letter_id=letter_id,
        event_type="comment_letter.approved",
        payload={
            "letter_id": letter_id,
            "approved_by": approved_by,
            "approved_at": _iso(ts),
        },
        store=store,
        organization_id=auth_context.organization_id,
        trace_id=trace_id,
        occurred_at=ts,
        produced_by="stage1a-review-service",
    )

    _set_letter_state(letter, "completed")
    letter["approved_at"] = _iso(ts)
    letter["completed_at"] = _iso(ts)
    letter["updated_at"] = _iso(ts)

    return 200, {
        "letter_id": letter_id,
        "approved_by": approved_by,
        "approved_at": _iso(ts),
        "snapshot_id": snapshot_id,
    }


def get_approval_snapshot(*, letter_id: str, auth_context: AuthContext, store: Stage1AStore) -> tuple[int, dict]:
    letter = store.letters_by_id.get(letter_id)
    if not letter:
        raise Stage1ARequestError(404, "not_found", "comment letter not found")
    if letter["organization_id"] != auth_context.organization_id:
        raise Stage1ARequestError(403, "forbidden", "comment letter belongs to another organization")

    snapshot = store.approval_snapshots_by_letter.get(letter_id)
    if not snapshot:
        raise Stage1ARequestError(404, "not_found", "approval snapshot not found")

    return 200, dict(snapshot)
