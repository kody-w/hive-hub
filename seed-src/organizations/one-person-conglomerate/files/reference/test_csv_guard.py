import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("csv_guard_reference", HERE / "csv_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class CsvGuardTests(unittest.TestCase):
    def test_clean_quoted_csv(self):
        result = guard.analyze_text('id,label\none,"paper, blue"\n', ["id"], "id")
        self.assertTrue(result["ok"])
        self.assertEqual(result["records"], 1)

    def test_supplied_duplicate(self):
        text = (HERE.parent / "data/csv-intake.csv").read_text(encoding="utf-8")
        result = guard.analyze_text(text, ["classification", "invoice-id", "amount-usd"], "invoice-id")
        self.assertEqual(result["findings"], [{"code": "duplicate-key", "record": 5, "column": 2}])

    def test_header_ambiguity(self):
        codes = [item["code"] for item in guard.analyze_text("id,id\none,two\n", key="id")["findings"]]
        self.assertEqual(codes, ["duplicate-header", "invalid-key-column"])

    def test_ragged_record(self):
        self.assertEqual(guard.analyze_text("id,label\none\n")["findings"][0]["code"], "ragged-row")

    def test_missing_and_blank(self):
        result = guard.analyze_text("id,label\n,hello\n", ["id", "amount"], "id")
        self.assertEqual([x["code"] for x in result["findings"]], ["missing-required-column", "blank-required-value", "blank-key"])

    def test_formula_is_only_text(self):
        result = guard.analyze_text("id,value\none,=1+1\n")
        self.assertEqual(result["findings"], [{"code": "spreadsheet-formula-risk", "record": 2, "column": 2}])

    def test_multiline_record_number(self):
        result = guard.analyze_text('id,label\none,"first\nsecond"\none,third\n', key="id")
        self.assertEqual(result["findings"][0]["record"], 3)

    def test_malformed_and_empty(self):
        for text in ("", "\n", 'id\n"unfinished', "id\n\x00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                guard.analyze_text(text)

    def test_size_limit(self):
        with self.assertRaises(ValueError):
            guard.analyze_text("x" * (guard.MAX_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
