import copy
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
SPEC = importlib.util.spec_from_file_location("line_ledger_reference", HERE / "line_ledger.py")
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.events = ledger.load_events(DATA / "events-clean.jsonl")

    def test_clean_contract(self):
        expected = json.loads((DATA / "expected-contract.json").read_text(encoding="utf-8"))["cases"][0]["expected"]
        self.assertEqual(ledger.reduce_events(self.events), expected)

    def test_known_duplicate_defect_is_present(self):
        actual = ledger.reduce_events(ledger.load_events(DATA / "events-duplicate.jsonl"))
        self.assertEqual(actual["event_count"], 4)
        self.assertEqual(actual["items"][0]["event_count"], 3)

    def test_known_arrival_order_defect_is_present(self):
        actual = ledger.reduce_events(ledger.load_events(DATA / "events-out-of-order.jsonl"))
        self.assertEqual(actual["items"][0]["state"], "open")
        self.assertEqual(actual["items"][0]["last_minute"], 10)

    def test_no_input_mutation(self):
        before = copy.deepcopy(self.events)
        self.assertEqual(ledger.reduce_events(self.events), ledger.reduce_events(self.events))
        self.assertEqual(self.events, before)

    def test_conflicting_duplicate_rejected(self):
        changed = dict(self.events[0], action="close")
        with self.assertRaisesRegex(ValueError, "conflicting event_id"):
            ledger.reduce_events(self.events + [changed])

    def test_invalid_action_and_extra_field(self):
        for event in (dict(self.events[0], action="archive"), dict(self.events[0], extra="inert-text")):
            with self.subTest(event=event), self.assertRaises(ValueError):
                ledger.reduce_events([event])

    def test_minute_bounds_and_boolean(self):
        for minute in (-1, 1_000_001, 1.5, True, "10"):
            with self.subTest(minute=minute), self.assertRaises(ValueError):
                ledger.reduce_events([dict(self.events[0], at_minute=minute)])

    def test_non_synthetic_input_rejected(self):
        with self.assertRaises(ValueError):
            ledger.reduce_events([dict(self.events[0], classification="unspecified")])

    def test_empty_and_blank_inputs(self):
        self.assertEqual(ledger.reduce_events(ledger.parse_text("\n  \n")), {"event_count": 0, "open_items": 0, "closed_items": 0, "items": []})

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            ledger.parse_text('{"classification":"SYNTHETIC","classification":"SYNTHETIC"}')

    def test_input_limits(self):
        with self.assertRaises(ValueError):
            ledger.parse_text(" " * (ledger.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            ledger.parse_text(" " * 16385)
        with self.assertRaises(ValueError):
            ledger.reduce_events([self.events[0]] * (ledger.MAX_EVENTS + 1))

    def test_id_shape_and_missing_fields(self):
        for event in (dict(self.events[0], item_id="not allowed"), {"classification": "SYNTHETIC"}, None):
            with self.subTest(event=event), self.assertRaises(ValueError):
                ledger.reduce_events([event])


if __name__ == "__main__":
    unittest.main()
