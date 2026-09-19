import copy
import importlib.util
import itertools
import json
import random
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packing = load_module("packing_tests", "tote_pack.py")
experiment = load_module("experiment_tests", "run_experiment.py")


class PackingTests(unittest.TestCase):
    def setUp(self):
        self.scenarios, self.capacity = packing.load_problem(DATA)

    def test_original_dataset_counts(self):
        self.assertEqual({key: len(value) for key, value in self.scenarios.items()}, {"order-trap": 4, "weight-trap": 8, "mixed-classroom": 14, "bulky-gaps": 3})
        self.assertEqual(sum(map(len, self.scenarios.values())), 29)

    def test_all_baseline_counts_and_model_proofs(self):
        expected = json.loads((HERE / "expected-baseline.json").read_text(encoding="utf-8"))["scenarios"]
        actual = packing.analyze(DATA, exact=True)
        for row in actual["scenarios"]:
            with self.subTest(scenario=row["scenario"]):
                target = expected[row["scenario"]]
                self.assertEqual(row["item_count"], target["item_count"])
                self.assertEqual(row["lower_bound"], target["lower_bound"])
                for method in packing.ALGORITHMS:
                    self.assertEqual(row["algorithms"][method]["bin_count"], target[method])
                self.assertTrue(row["model_proof"]["proven"])
                self.assertEqual(row["model_proof"]["best_count"], target["model_optimum"])

    def test_every_assignment_is_feasible(self):
        for items in self.scenarios.values():
            for algorithm in packing.ALGORITHMS:
                self.assertTrue(packing.verify(items, packing.pack(items, self.capacity, algorithm), self.capacity))

    def test_pure_and_deterministic(self):
        items = self.scenarios["mixed-classroom"]
        before = copy.deepcopy(items)
        first = packing.pack(items, self.capacity)
        self.assertEqual(first, packing.pack(items, self.capacity))
        self.assertEqual(items, before)

    def test_sorted_methods_are_permutation_invariant(self):
        for items in self.scenarios.values():
            for algorithm in ("dominant-first-fit", "volume-first-fit"):
                self.assertEqual(packing.pack(items, self.capacity, algorithm), packing.pack(list(reversed(items)), self.capacity, algorithm))

    def test_duplicate_and_oversized_inputs(self):
        items = self.scenarios["order-trap"]
        with self.assertRaises(ValueError):
            packing.pack(items + [items[0]], self.capacity)
        with self.assertRaises(ValueError):
            packing.pack([dict(items[0], volume=11)], self.capacity)
        with self.assertRaises(ValueError):
            packing.pack([dict(items[0], weight=0)], self.capacity)
        with self.assertRaises(ValueError):
            packing.pack([dict(items[0], weight=True)], self.capacity)

    def test_verifier_detects_missing_and_incorrect_load(self):
        items = self.scenarios["order-trap"]
        bins = packing.pack(items, self.capacity)
        with self.assertRaises(ValueError):
            packing.verify(items, bins[:-1], self.capacity)
        bins[0]["weight_used"] += 1
        with self.assertRaises(ValueError):
            packing.verify(items, bins, self.capacity)

    def test_empty_model(self):
        self.assertEqual(packing.pack([], self.capacity), [])
        self.assertEqual(packing.lower_bound([], self.capacity), 0)
        self.assertEqual(packing.exact_minimum([], self.capacity)["best_count"], 0)

    def test_search_proves_indivisibility_gap(self):
        result = packing.exact_minimum(self.scenarios["bulky-gaps"], self.capacity)
        self.assertEqual((result["best_count"], result["lower_bound"], result["method"]), (3, 2, "bounded-search"))
        self.assertGreater(result["nodes"], 0)

    def test_node_limit_is_not_a_proof(self):
        result = packing.exact_minimum(self.scenarios["bulky-gaps"], self.capacity, node_limit=1)
        self.assertFalse(result["proven"])
        self.assertEqual(result["method"], "node-limit-unproven")

    def test_large_unclosed_bound_skips_search(self):
        items = [{"id": f"bulky-{index}", "volume": 6, "weight": 1} for index in range(13)]
        result = packing.exact_minimum(items, self.capacity)
        self.assertFalse(result["proven"])
        self.assertEqual(result["method"], "skipped-item-limit")

    def test_exact_search_matches_small_exhaustive_assignments(self):
        rng = random.Random(74)
        for case in range(8):
            items = [{"id": f"sample-{index}", "volume": rng.randint(1, 9), "weight": rng.randint(1, 9)} for index in range(5)]
            optimum = len(items)
            for assignment in itertools.product(range(len(items)), repeat=len(items)):
                used = set(assignment)
                if len(used) >= optimum:
                    continue
                if all(
                    sum(item["volume"] for item, target in zip(items, assignment) if target == bin_id) <= 10
                    and sum(item["weight"] for item, target in zip(items, assignment) if target == bin_id) <= 10
                    for bin_id in used
                ):
                    optimum = len(used)
            result = packing.exact_minimum(items, self.capacity)
            with self.subTest(case=case):
                self.assertTrue(result["proven"])
                self.assertEqual(result["best_count"], optimum)

    def test_seeded_experiment_replicates_all_trials(self):
        first = experiment.run(DATA)
        self.assertEqual(first, experiment.run(DATA))
        self.assertEqual(first["repetitions"], 20)
        self.assertEqual(len(first["source_sha256"]), 3)
        trial_count = 0
        for scenario in first["scenarios"]:
            for algorithm, result in scenario["algorithms"].items():
                self.assertEqual(len(result["counts"]), 20)
                trial_count += len(result["counts"])
                if algorithm != "input-first-fit":
                    self.assertEqual(len(set(result["counts"])), 1)
        self.assertEqual(trial_count, 240)


if __name__ == "__main__":
    unittest.main()
