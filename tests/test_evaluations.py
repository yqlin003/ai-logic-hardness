import unittest

from evaluations.score import evaluate_items, normalize_answer, score_answer


class EvaluationTests(unittest.TestCase):
    def test_normalization_handles_code_fence_and_whitespace(self):
        self.assertEqual(normalize_answer("```text\n  A   B C\n```"), "a b c")

    def test_exact_answer_scores_full_credit(self):
        result = score_answer("4 km/h", "4 km/h")
        self.assertTrue(result["exact"])
        self.assertEqual(result["correctness"], 1.0)

    def test_wrong_answer_scores_zero(self):
        result = score_answer("5", "10")
        self.assertFalse(result["exact"])
        self.assertEqual(result["correctness"], 0.0)

    def test_evaluate_items_reports_accuracy(self):
        items = [
            {"id": "a", "reference_answer": "A B C"},
            {"id": "b", "reference_answer": "5"},
        ]
        report = evaluate_items(items, {"a": "A B C", "b": "10"})
        self.assertEqual(report["correct"], 1)
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
