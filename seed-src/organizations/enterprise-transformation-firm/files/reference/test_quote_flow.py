import copy
import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SPEC = importlib.util.spec_from_file_location("quote_flow_reference", HERE / "quote_flow.py")
flow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flow)


class QuoteFlowTests(unittest.TestCase):
    def setUp(self):
        self.quote = flow.read_csv(DATA / "quotes.csv")[0]
        self.lines = [flow.read_csv(DATA / "quote-lines.csv")[0]]
        self.account = flow.read_csv(DATA / "accounts.csv")[0]
        self.policy = json.loads((DATA / "policy.json").read_text(encoding="utf-8"))

    def test_all_eight_expected_cases(self):
        result = flow.run_batch(DATA)
        expected = json.loads((HERE / "expected-results.json").read_text(encoding="utf-8"))
        actual = [{
            "quote_id": row["quote_id"], "state": row["state"],
            "total_usd": row["totals"]["total_usd"] if row["totals"] else None,
            "data_errors": row["data_errors"], "review_reasons": row["review_reasons"],
        } for row in result["quotes"]]
        self.assertEqual(actual, expected["quotes"])
        self.assertEqual(result["counts"], {"needs-data": 2, "needs-review": 4, "ready-for-human-approval": 2})

    def test_no_mutation_and_determinism(self):
        before = copy.deepcopy((self.quote, self.lines, self.account, self.policy))
        a = flow.evaluate(self.quote, self.lines, self.account, self.policy)
        self.assertEqual(a, flow.evaluate(self.quote, self.lines, self.account, self.policy))
        self.assertEqual(before, (self.quote, self.lines, self.account, self.policy))

    def test_credit_equality_is_not_breach(self):
        self.account["credit-limit-usd"] = "4768.21"
        self.assertNotIn("credit-limit", flow.evaluate(self.quote, self.lines, self.account, self.policy)["review_reasons"])

    def test_half_up_boundary(self):
        self.assertEqual(flow.cents(Decimal("849.915")), Decimal("849.92"))
        self.assertEqual(flow.cents(Decimal("0.01125")), Decimal("0.01"))

    def test_unknown_account(self):
        result = flow.evaluate(self.quote, self.lines, None, self.policy)
        self.assertEqual(result["data_errors"], ["unknown-account"])
        self.assertIsNone(result["totals"])

    def test_duplicate_and_or_mismatched_lines(self):
        duplicate = flow.evaluate(self.quote, self.lines * 2, self.account, self.policy)
        self.assertIn("line-101-a:duplicate-line", duplicate["data_errors"])
        self.lines[0]["quote-id"] = "q-other"
        self.assertIn("line-101-a:quote-mismatch", flow.evaluate(self.quote, self.lines, self.account, self.policy)["data_errors"])

    def test_bad_numbers(self):
        for bad in ("NaN", "Infinity", "-0.01", "0.001"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                flow.amount(bad, "test")

    def test_invalid_quantity_variants(self):
        for bad in ("0", "-1", "1.5", "10001", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                flow.integer(bad, "quantity", 10000)

    def test_missing_data_precedes_review(self):
        self.quote["po-reference"] = ""
        self.account["active"] = "no"
        result = flow.evaluate(self.quote, self.lines, self.account, self.policy)
        self.assertEqual(result["state"], "needs-data")
        self.assertIn("inactive-account", result["review_reasons"])
        self.assertIsNone(result["totals"])

    def test_duplicate_account_keys(self):
        with self.assertRaises(ValueError):
            flow.keyed([self.account, self.account], "account-id")

    def test_empty_lines_block(self):
        self.assertIn("missing-lines", flow.evaluate(self.quote, [], self.account, self.policy)["data_errors"])

    def test_non_synthetic_inputs_are_not_relabeled(self):
        self.quote["classification"] = "unspecified"
        with self.assertRaisesRegex(ValueError, "SYNTHETIC"):
            flow.evaluate(self.quote, self.lines, self.account, self.policy)


if __name__ == "__main__":
    unittest.main()
