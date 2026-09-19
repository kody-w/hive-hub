"""Exercise local rejection/rework without implying partner or owner authority."""
import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prime_acceptance", ROOT / "tools/acceptance.py")
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.configuration = ACCEPTANCE.load_configuration()
        self.fixture = ACCEPTANCE.read_json("fixtures/rework-submissions.json")

    def evaluate(self, fixture=None):
        return ACCEPTANCE.evaluate(self.configuration, self.fixture if fixture is None else fixture, "fixtures/rework-submissions.json")

    def test_machine_briefs_matrix_and_topology_conform(self):
        self.assertEqual(self.configuration["order"], ["prototype-spec", "operating-model", "pilot-kit", "integration-report"])
        self.assertEqual(len(self.configuration["matrix"]), 18)
        for row in self.configuration["matrix"]:
            self.assertTrue(row["citation"].startswith("data/acceptance-matrix.csv#row="))

    def test_baseline_explicit_rejection_and_downstream_block(self):
        report = ACCEPTANCE.run("baseline")
        self.assertFalse(report["content_pass"])
        self.assertEqual(report["counts"], {"content-pass": 1, "rejected": 2, "blocked": 1, "missing": 0})
        rows = {row["deliverable_id"]: row for row in report["deliverables"]}
        self.assertEqual(rows["operating-model"]["failures"], ["operations-retention: content criterion not satisfied"])
        self.assertEqual(rows["pilot-kit"]["failures"], ["kit-interface: content criterion not satisfied"])
        self.assertEqual(rows["integration-report"]["content_status"], "blocked")
        self.assertEqual(len(report["rework_requests"]), 2)
        self.assertTrue(all(not request["request_sent"] for request in report["rework_requests"]))

    def test_rework_pass_never_becomes_authority(self):
        report = ACCEPTANCE.run("rework")
        self.assertTrue(report["content_pass"])
        self.assertEqual(report["counts"]["content-pass"], 4)
        self.assertEqual(sum(len(row["checks"]) for row in report["deliverables"]), 18)
        for key in ("delivery_authorized", "real_partner_submissions", "foreign_workspace_registration", "federation_activation", "approved_contract", "membership_created", "remote_authority"):
            self.assertIs(report[key], False)
        self.assertEqual(report["owner_exchange_approval"], "not-requested")
        self.assertEqual(report["external_effects"], [])

    def test_missing_upstream_blocks_all_dependents(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["submissions"] = fixture["submissions"][1:]
        report = self.evaluate(fixture)
        self.assertEqual(report["counts"], {"content-pass": 0, "rejected": 0, "blocked": 3, "missing": 1})

    def test_wrong_candidate_is_rejected_not_registered(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["submissions"][0]["candidate_partner"] = "unlisted-candidate"
        report = self.evaluate(fixture)
        self.assertEqual(report["deliverables"][0]["content_status"], "rejected")
        self.assertFalse(report["foreign_workspace_registration"])

    def test_private_or_claimed_approval_metadata_is_rejected(self):
        for change in ({"artifact_visibility": "private"}, {"exchange_approval": "approved"}):
            fixture = copy.deepcopy(self.fixture)
            fixture["submissions"][0].update(change)
            with self.subTest(change=change):
                report = self.evaluate(fixture)
                self.assertFalse(report["content_pass"])
                self.assertFalse(report["delivery_authorized"])

    def test_extra_fields_and_field_list_expansion_fail(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["submissions"][0]["artifact"]["extra_unapproved_field"] = "synthetic-example"
        self.assertFalse(self.evaluate(fixture)["content_pass"])
        fixture = copy.deepcopy(self.fixture)
        fixture["submissions"][0]["artifact"]["record_fields"].append("unapproved_identifier")
        self.assertFalse(self.evaluate(fixture)["content_pass"])

    def test_duplicate_and_undeclared_submissions_fail(self):
        duplicate = copy.deepcopy(self.fixture)
        duplicate["submissions"].append(copy.deepcopy(duplicate["submissions"][0]))
        with self.assertRaises(ValueError):
            self.evaluate(duplicate)
        unknown = copy.deepcopy(self.fixture)
        unknown["submissions"][0]["deliverable_id"] = "unapproved-extra-delivery"
        with self.assertRaises(ValueError):
            self.evaluate(unknown)

    def test_cyclic_and_unknown_dependencies_fail(self):
        rows = self.configuration["deliverables"]
        edges = [{"deliverable_id": "prototype-spec", "depends_on": "operating-model"}, {"deliverable_id": "operating-model", "depends_on": "prototype-spec"}]
        with self.assertRaises(ValueError):
            ACCEPTANCE.dependency_order(rows, edges)
        with self.assertRaises(ValueError):
            ACCEPTANCE.dependency_order(rows, [{"deliverable_id": "prototype-spec", "depends_on": "unknown"}])

    def test_rules_are_typed_and_fail_closed(self):
        self.assertFalse(ACCEPTANCE.matches("equals", 1, True))
        self.assertFalse(ACCEPTANCE.matches("integer-between", True, [1, 120]))
        self.assertFalse(ACCEPTANCE.matches("integer-between", 1440, [1, 120]))
        self.assertFalse(ACCEPTANCE.matches("integer-between", 0, [1, 120]))
        self.assertFalse(ACCEPTANCE.matches("equals", ACCEPTANCE.MISSING, False))
        self.assertFalse(ACCEPTANCE.matches("set-equals", ["a", "a"], ["a"]))
        self.assertFalse(ACCEPTANCE.matches("nonempty-strings-min", ["one", "", "three", "four"], 4))
        with self.assertRaises(ValueError):
            ACCEPTANCE.matches("execute-python", "inert", "inert")
        with self.assertRaises(ValueError):
            ACCEPTANCE.matches("integer-between", 10, [120, 1])

    def test_numeric_scope_change_is_rejected(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["submissions"][0]["artifact"]["max_demo_attendees"] = 90
        report = self.evaluate(fixture)
        self.assertFalse(report["content_pass"])
        self.assertIn("prototype-capacity: content criterion not satisfied", report["deliverables"][0]["failures"])

    def test_malformed_json_and_unlisted_paths_are_not_accepted(self):
        with self.assertRaises(ValueError):
            ACCEPTANCE.decode_json('{"classification":"SYNTHETIC","classification":"other"}')
        with self.assertRaises(ValueError):
            ACCEPTANCE.decode_json('{"value":NaN}')
        with self.assertRaises(ValueError):
            ACCEPTANCE.run("../other.json")

    def test_fixture_not_real_input_and_no_mutation(self):
        before = copy.deepcopy(self.fixture)
        self.evaluate()
        self.assertEqual(before, self.fixture)
        invalid = copy.deepcopy(self.fixture)
        invalid["fixture_only"] = False
        with self.assertRaises(ValueError):
            self.evaluate(invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
