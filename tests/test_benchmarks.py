import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "logic_hard_v1.json"


class BenchmarkSchemaTests(unittest.TestCase):
    def setUp(self):
        with BENCHMARK.open(encoding="utf-8") as handle:
            self.data = json.load(handle)

    def test_benchmark_has_unique_valid_items(self):
        items = self.data["items"]
        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(items), 3)

        for item in items:
            self.assertIn(item["category"], {
                "constraint-satisfaction",
                "state-tracking",
                "quantitative-reasoning",
            })
            self.assertIsInstance(item["difficulty"], int)
            self.assertIn("prompt", item)
            self.assertIn("reference_answer", item)
            self.assertGreaterEqual(len(item["rubric"]), 2)
            self.assertGreaterEqual(len(item["perturbations"]), 2)


if __name__ == "__main__":
    unittest.main()
