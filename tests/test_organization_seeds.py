from __future__ import annotations

import copy
import json
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hive_hub import AIJoinCard
from scripts.check_organization_seeds import verify_package
from scripts.organization_seeds import (
    ROOT,
    SEED_SLUGS,
    build_seed,
    load_blueprint,
    validate_blueprint,
)


class OrganizationSeedTests(unittest.TestCase):
    def test_each_seed_camera_card_matches_the_locked_dialbook(self) -> None:
        dialbook = json.loads((ROOT / "skills/hive-hub/registry/public-dialbook.json").read_text())
        records = {
            record["aliases"][0]: record for record in dialbook["records"] if record["aliases"]
        }
        for slug in SEED_SLUGS:
            with self.subTest(slug=slug):
                card = AIJoinCard.from_dict(
                    json.loads((ROOT / "public-src/cards" / f"seed-{slug}-core.json").read_text())
                )
                self.assertEqual(card.locator, records[slug]["id"])
                self.assertIsNone(card.adapter_plan)

    def test_all_ten_are_substantial_portable_packages(self) -> None:
        worlds: set[str] = set()
        for slug in SEED_SLUGS:
            with self.subTest(slug=slug):
                seed = build_seed(slug)
                files = verify_package(seed)
                self.assertGreaterEqual(seed["counts"]["teams"], 5)
                self.assertGreaterEqual(seed["counts"]["tasks"], 6)
                self.assertGreaterEqual(seed["counts"]["starterFiles"], 6)
                setup = json.loads(files["initialize.json"])
                self.assertEqual(setup["organization"]["scaffold"]["kind"], "organization")
                self.assertFalse(setup["external_effects_authorized"])
                self.assertFalse(setup["signed_estate_activation"])
                world = setup["organization"]["scaffold"]["world_id"]
                self.assertNotIn(world, worlds)
                worlds.add(world)
                for member in setup["workspaces"]:
                    self.assertEqual(member["scaffold"]["world_id"], world)
                    self.assertEqual(member["scaffold"]["kind"], "workspace")
                    self.assertTrue(
                        any(path.startswith(member["template"] + "/") for path in files)
                    )
                self.assertTrue(any(task["state"] == "ready" for task in seed["tasks"]))
                self.assertTrue(all(not task["completed_evidence"] for task in seed["tasks"]))
                self.assertFalse(
                    any(Path(path).name in {"rappid.json", "organization.json"} for path in files)
                )
                self.assertTrue(
                    any(
                        "/starter/" in path
                        and Path(path).suffix in {".py", ".html", ".js", ".scad", ".svg"}
                        for path in files
                    ),
                    "A seed must contain a usable artifact, not just prose.",
                )

    def test_generated_package_is_exactly_reproducible(self) -> None:
        for slug in SEED_SLUGS:
            expected = build_seed(slug)
            generated = json.loads(
                (ROOT / "public-src/organization-seeds" / f"{slug}.json").read_text()
            )
            self.assertEqual(expected, generated)

    def test_invalid_ownership_cycles_and_unbound_inputs_are_refused(self) -> None:
        slug = SEED_SLUGS[0]
        original, _ = load_blueprint(slug)
        mutations: list[Callable[[dict[str, Any]], None]] = [
            lambda value: value["tasks"][0].update(team="undeclared-owner"),
            lambda value: value["tasks"][0].update(depends_on=[value["tasks"][0]["id"]]),
            lambda value: value["tasks"][0].update(inputs=["undeclared-input.csv"]),
            lambda value: value["tasks"][0].update(outputs=["../escaped-output"]),
            lambda value: value["files"].append("../private-book.json"),
        ]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate_blueprint(value, slug)

    def test_package_and_archive_tampering_are_refused(self) -> None:
        original = build_seed(SEED_SLUGS[0])
        changed_file = copy.deepcopy(original)
        changed_file["files"][0]["content"] += "\nnot approved"
        with self.assertRaises(ValueError):
            verify_package(changed_file)
        changed_archive = copy.deepcopy(original)
        changed_archive["archive"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_package(changed_archive)


if __name__ == "__main__":
    unittest.main()
