"""Exact-citation and arithmetic tests for the authored local corpus."""
import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("local_evidence", ROOT / "tools/evidence.py")
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.records = EVIDENCE.load_corpus()

    def test_inventory_and_citation_audit(self):
        report = EVIDENCE.audit(self.records)
        self.assertEqual((report["source_files"], report["source_records"], report["coded_claims"], report["conflict_cases"], report["prospective_inquiries"]), (5, 18, 9, 3, 6))
        self.assertTrue(report["references_resolve"])
        self.assertEqual(report["external_effects"], [])

    def test_citations_are_exact_physical_rows_and_hashes(self):
        for record in self.records:
            source = ROOT / record["source_file"]
            physical_line = source.read_text(encoding="utf-8").splitlines()[record["csv_row"] - 1]
            self.assertTrue(physical_line.startswith(record["record_id"] + ","))
            self.assertEqual(record["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(record["citation"], f'{record["source_file"]}#row={record["csv_row"]}')

    def test_timeline_is_stable_and_bounded(self):
        ordered = EVIDENCE.timeline(list(reversed(self.records)))
        self.assertEqual(ordered, EVIDENCE.timeline(self.records))
        self.assertEqual(ordered[0]["published_at"], "2026-09-01")
        self.assertEqual(ordered[-1]["published_at"], "2026-09-17")

    def test_case_insensitive_offline_search(self):
        lower, upper = EVIDENCE.search(self.records, "restart"), EVIDENCE.search(self.records, "RESTART")
        self.assertEqual(lower, upper)
        self.assertGreater(len(lower), 4)
        self.assertEqual(EVIDENCE.search(self.records, "no-such-authored-term"), [])
        with self.assertRaises(ValueError):
            EVIDENCE.search(self.records, " ")

    def test_benchmark_conditions_are_not_pooled(self):
        report = EVIDENCE.audit(self.records)
        metrics = {row["record_id"]: row for row in report["run_metrics"]}
        self.assertEqual(metrics["run-01"]["acknowledgment_fraction"], "0.987")
        self.assertIsNone(metrics["run-01"]["recovered_ids"])
        self.assertIsNone(metrics["run-02"]["acknowledged_ids_unreconciled"])
        self.assertEqual(metrics["run-02"]["acknowledged"], 0)
        self.assertEqual(metrics["run-03"]["acknowledged"], 0)
        self.assertEqual(metrics["run-04"]["acknowledgment_fraction"], "0.995")
        self.assertEqual(metrics["run-04"]["acknowledged_ids_unreconciled"], 8)
        self.assertEqual(report["qualifying_runs"], 0)
        self.assertIsNone(report["pooled_reliability"])

    def test_invalid_and_outside_citations_fail_closed(self):
        index = {row["citation"]: row for row in self.records}
        for reference in ("sources/announcements.csv#row=1", "sources/announcements.csv#row=999", "../outside.csv#row=2", "https://invalid.example/source", "sources/announcements.csv#row=2;sources/announcements.csv#row=2"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                EVIDENCE.resolve_refs(reference, index)

    def test_missing_or_duplicate_source_breaks_audit(self):
        with self.assertRaises(ValueError):
            EVIDENCE.audit(self.records[1:])
        with self.assertRaises(ValueError):
            EVIDENCE.audit(self.records + [self.records[0]])

    def test_benchmark_bad_counts_are_rejected(self):
        base = next(row["original_fields"] for row in self.records if row["record_id"] == "run-04")
        for changes in ({"attempted": "0"}, {"acknowledged": "401"}, {"recovered_ids": "399"}, {"cold_restart": "2"}, {"offline_hours": "NaN"}, {"attempted": "-1"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                EVIDENCE.benchmark_metrics({**base, **changes})

    def test_gate_requires_recovered_ids_and_nonzero_acknowledgments(self):
        base = next(row["original_fields"] for row in self.records if row["record_id"] == "run-04")
        good = {**base, "offline_hours": "72", "recovered_ids": "398"}
        self.assertTrue(EVIDENCE.benchmark_metrics(good)["meets_duration_restart_recovery_gate"])
        for changes in ({"recovered_ids": ""}, {"cold_restart": "0"}, {"offline_hours": "71"}, {"acknowledged": "0", "recovered_ids": "0"}):
            self.assertFalse(EVIDENCE.benchmark_metrics({**good, **changes})["meets_duration_restart_recovery_gate"])

    def test_metric_reproduction_does_not_mutate_records(self):
        before = copy.deepcopy(self.records)
        EVIDENCE.audit(self.records)
        self.assertEqual(before, self.records)


if __name__ == "__main__":
    unittest.main(verbosity=2)
