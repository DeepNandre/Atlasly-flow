from __future__ import annotations

from dataclasses import dataclass
from statistics import median
import math


@dataclass(frozen=True)
class Stage1AMetrics:
    discipline_precision: float
    comment_capture_recall: float
    hallucinated_code_reference_rate: float
    median_latency_seconds: float
    p95_latency_seconds: float
    review_queue_rate: float
    reviewer_correction_rate: float


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _span_iou(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    if inter <= 0:
        return 0.0
    union = max(a_end, b_end) - min(a_start, b_start)
    if union <= 0:
        return 0.0
    return inter / union


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(math.ceil(0.95 * len(ordered))) - 1
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]


def evaluate_benchmark(
    *,
    predictions: list[dict],
    gold: list[dict],
    latency_seconds: list[float],
) -> Stage1AMetrics:
    gold_unmatched = set(range(len(gold)))
    discipline_tp = 0
    matched_pred = 0

    for pred in predictions:
        best_idx = None
        best_score = 0.0
        pred_page = int(pred.get("page_number", 0))
        pred_start = int(pred.get("citation_char_start", 0))
        pred_end = int(pred.get("citation_char_end", 0))

        for idx in list(gold_unmatched):
            g = gold[idx]
            if int(g.get("page_number", 0)) != pred_page:
                continue
            iou = _span_iou(
                pred_start,
                pred_end,
                int(g.get("citation_char_start", 0)),
                int(g.get("citation_char_end", 0)),
            )
            if iou > best_score:
                best_score = iou
                best_idx = idx

        if best_idx is not None and best_score >= 0.6:
            matched_pred += 1
            gold_unmatched.discard(best_idx)
            if str(pred.get("discipline")) == str(gold[best_idx].get("discipline")):
                discipline_tp += 1

    precision = 0.0 if not predictions else discipline_tp / len(predictions)
    recall = 0.0 if not gold else matched_pred / len(gold)

    code_ref_total = 0
    code_ref_bad = 0
    for pred in predictions:
        code_ref = str(pred.get("code_reference") or "").strip()
        if not code_ref:
            continue
        code_ref_total += 1
        has_citation = bool(str(pred.get("citation_quote") or "").strip())
        valid_format = bool(pred.get("code_reference_valid_format", False))
        if not has_citation or not valid_format:
            code_ref_bad += 1

    hallucination_rate = 0.0 if code_ref_total == 0 else code_ref_bad / code_ref_total

    review_count = sum(1 for pred in predictions if pred.get("status") == "needs_review")
    corrected_count = sum(1 for pred in predictions if pred.get("status") == "reviewed_corrected")

    median_latency = median(latency_seconds) if latency_seconds else 0.0
    p95_latency = _p95(latency_seconds)

    return Stage1AMetrics(
        discipline_precision=round(_clamp01(precision), 4),
        comment_capture_recall=round(_clamp01(recall), 4),
        hallucinated_code_reference_rate=round(_clamp01(hallucination_rate), 4),
        median_latency_seconds=round(float(median_latency), 3),
        p95_latency_seconds=round(float(p95_latency), 3),
        review_queue_rate=round(_clamp01(review_count / len(predictions) if predictions else 0.0), 4),
        reviewer_correction_rate=round(_clamp01(corrected_count / len(predictions) if predictions else 0.0), 4),
    )


def release_gate_decision(*, metrics: Stage1AMetrics, target: str) -> tuple[bool, list[str]]:
    if target not in {"staging", "prod"}:
        raise ValueError("target must be 'staging' or 'prod'")

    reasons: list[str] = []

    if target == "staging":
        if metrics.discipline_precision < 0.88:
            reasons.append("discipline_precision < 0.88")
        if metrics.comment_capture_recall < 0.82:
            reasons.append("comment_capture_recall < 0.82")
        if metrics.median_latency_seconds > 12 * 60:
            reasons.append("median_latency_seconds > 720")
        if metrics.hallucinated_code_reference_rate > 0.08:
            reasons.append("hallucinated_code_reference_rate > 0.08")
    else:
        if metrics.discipline_precision < 0.90:
            reasons.append("discipline_precision < 0.90")
        if metrics.comment_capture_recall < 0.85:
            reasons.append("comment_capture_recall < 0.85")
        if metrics.median_latency_seconds > 10 * 60:
            reasons.append("median_latency_seconds > 600")
        if metrics.p95_latency_seconds > 18 * 60:
            reasons.append("p95_latency_seconds > 1080")
        if metrics.hallucinated_code_reference_rate > 0.05:
            reasons.append("hallucinated_code_reference_rate > 0.05")

    return len(reasons) == 0, reasons
