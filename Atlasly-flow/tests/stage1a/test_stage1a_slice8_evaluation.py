import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage1a.evaluation import Stage1AMetrics
from scripts.stage1a.evaluation import evaluate_benchmark
from scripts.stage1a.evaluation import release_gate_decision


class Stage1ASlice8EvaluationTests(unittest.TestCase):
    def test_evaluate_benchmark_metrics(self):
        predictions = [
            {
                "page_number": 1,
                "citation_char_start": 10,
                "citation_char_end": 30,
                "discipline": "electrical",
                "code_reference": "NEC 408.4",
                "code_reference_valid_format": True,
                "citation_quote": "panel schedule",
                "status": "auto_accepted",
            },
            {
                "page_number": 2,
                "citation_char_start": 40,
                "citation_char_end": 70,
                "discipline": "plumbing",
                "code_reference": "NOT-A-CODE",
                "code_reference_valid_format": False,
                "citation_quote": "",
                "status": "needs_review",
            },
        ]
        gold = [
            {
                "page_number": 1,
                "citation_char_start": 12,
                "citation_char_end": 32,
                "discipline": "electrical",
            },
            {
                "page_number": 2,
                "citation_char_start": 42,
                "citation_char_end": 72,
                "discipline": "mechanical",
            },
            {
                "page_number": 3,
                "citation_char_start": 5,
                "citation_char_end": 25,
                "discipline": "fire",
            },
        ]

        metrics = evaluate_benchmark(
            predictions=predictions,
            gold=gold,
            latency_seconds=[300.0, 540.0, 620.0, 400.0],
        )

        self.assertAlmostEqual(metrics.discipline_precision, 0.5)
        self.assertAlmostEqual(metrics.comment_capture_recall, 0.6667, places=4)
        self.assertAlmostEqual(metrics.hallucinated_code_reference_rate, 0.5)
        self.assertAlmostEqual(metrics.median_latency_seconds, 470.0)
        self.assertAlmostEqual(metrics.p95_latency_seconds, 620.0)
        self.assertAlmostEqual(metrics.review_queue_rate, 0.5)

    def test_release_gate_decision_staging_and_prod(self):
        strong = Stage1AMetrics(
            discipline_precision=0.92,
            comment_capture_recall=0.88,
            hallucinated_code_reference_rate=0.03,
            median_latency_seconds=540.0,
            p95_latency_seconds=1020.0,
            review_queue_rate=0.25,
            reviewer_correction_rate=0.1,
        )
        weak = Stage1AMetrics(
            discipline_precision=0.87,
            comment_capture_recall=0.80,
            hallucinated_code_reference_rate=0.10,
            median_latency_seconds=900.0,
            p95_latency_seconds=1300.0,
            review_queue_rate=0.45,
            reviewer_correction_rate=0.25,
        )

        staging_ok, staging_reasons = release_gate_decision(metrics=strong, target="staging")
        prod_ok, prod_reasons = release_gate_decision(metrics=strong, target="prod")
        self.assertTrue(staging_ok)
        self.assertTrue(prod_ok)
        self.assertEqual(staging_reasons, [])
        self.assertEqual(prod_reasons, [])

        weak_staging_ok, weak_staging_reasons = release_gate_decision(metrics=weak, target="staging")
        weak_prod_ok, weak_prod_reasons = release_gate_decision(metrics=weak, target="prod")
        self.assertFalse(weak_staging_ok)
        self.assertFalse(weak_prod_ok)
        self.assertGreaterEqual(len(weak_staging_reasons), 3)
        self.assertGreaterEqual(len(weak_prod_reasons), 4)


if __name__ == "__main__":
    unittest.main()
