import csv
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("allocation_reference", HERE / "allocation.py")
allocation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(allocation)


class AllocationTests(unittest.TestCase):
    def setUp(self):
        with (HERE.parent / "data/allocation-worksheet.csv").open(encoding="utf-8", newline="") as handle:
            self.rows = list(csv.DictReader(handle))
        self.capacity = json.loads((HERE.parent / "data/capacity.json").read_text(encoding="utf-8"))

    def test_reference_selection(self):
        actual = allocation.analyze(self.rows, self.capacity)["worksheet"]
        self.assertEqual((actual["hours"], actual["cost_usd"], actual["score_units"]), (19, "90.00", 3225))
        self.assertTrue(actual["feasible"])

    def test_recommendation(self):
        actual = allocation.analyze(self.rows, self.capacity)["recommendation"]
        self.assertEqual(actual["experiment_ids"], ["lf-schema", "qb-keyboard", "tl-sample"])
        self.assertEqual((actual["hours"], actual["cost_usd"], actual["score_units"]), (21, "90.00", 3800))

    def test_order_does_not_change_answer(self):
        self.assertEqual(allocation.analyze(self.rows, self.capacity), allocation.analyze(list(reversed(self.rows)), self.capacity))

    def test_zero_discretionary_capacity(self):
        self.capacity["reserved_hours"] = 40
        self.assertEqual(allocation.analyze(self.rows, self.capacity)["recommendation"]["experiment_ids"], [])

    def test_overallocated_worksheet_is_reported_not_hidden(self):
        for row in self.rows:
            row["selected"] = "1"
        actual = allocation.analyze(self.rows, self.capacity)
        self.assertFalse(actual["worksheet"]["feasible"])
        self.assertIn("multiple-experiments-per-unit", actual["worksheet"]["violations"])
        self.assertTrue(actual["recommendation"]["feasible"])

    def test_invalid_money(self):
        for value in ("-1", "NaN", "Infinity", "0.001", "1e100000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                allocation.money(value)

    def test_non_synthetic_inputs_are_not_relabeled(self):
        self.rows[0]["classification"] = "unspecified"
        with self.assertRaisesRegex(ValueError, "SYNTHETIC"):
            allocation.analyze(self.rows, self.capacity)

    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):
            allocation.analyze(self.rows + [self.rows[0]], self.capacity)

    def test_bounds(self):
        self.rows[0]["confidence-pct"] = "101"
        with self.assertRaises(ValueError):
            allocation.analyze(self.rows, self.capacity)

    def test_tie_break_uses_stable_id(self):
        first = dict(self.rows[0], **{"experiment-id": "a-test", "unit": "unit-a", "selected": "0"})
        second = dict(first, **{"experiment-id": "b-test", "unit": "unit-b"})
        self.capacity["max_active_businesses"] = 1
        self.assertEqual(allocation.analyze([second, first], self.capacity)["recommendation"]["experiment_ids"], ["a-test"])


if __name__ == "__main__":
    unittest.main()
