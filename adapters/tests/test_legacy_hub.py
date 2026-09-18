from __future__ import annotations

import importlib
import runpy
import subprocess
import unittest
import urllib.request
from unittest.mock import patch

from adapters.contracts import AccessOutcome, AdapterRefusal
from adapters.legacy_hub import LEGACY_COMPONENT, LegacyRappHubInspector
from adapters.tests.support import FIXTURES


class LegacyHubInspectorTests(unittest.TestCase):
    def test_historical_manifests_and_world_json_parse_inertly(self) -> None:
        inspector = LegacyRappHubInspector()
        with (
            patch.object(subprocess, "run") as ran,
            patch.object(urllib.request, "urlopen") as fetched,
            patch.object(importlib, "import_module") as imported,
            patch.object(runpy, "run_path") as executed,
        ):
            report = inspector.inspect(FIXTURES / "legacy_hub")
        self.assertEqual(report.component, LEGACY_COMPONENT)
        self.assertEqual(report.outcome, AccessOutcome.REACHABLE)
        self.assertFalse(report.authority)
        self.assertEqual(report.downloads, 0)
        self.assertEqual(report.installs, 0)
        self.assertEqual(report.imports, 0)
        self.assertEqual(report.executions, 0)
        self.assertEqual(len(report.dimensions), 1)
        dimension = report.dimensions[0]
        self.assertEqual(dimension.universe_id, "temporal")
        self.assertEqual(dimension.dimension_id, "nexus")
        self.assertEqual(dimension.seed, 2026)
        self.assertIn(
            "worlds/temporal/nexus/rappbook/posts/malicious.json",
            dimension.world_json_files,
        )
        record_paths = {record.path for record in report.records}
        self.assertNotIn(
            "worlds/temporal/nexus/never_import.py",
            record_paths,
        )
        ran.assert_not_called()
        fetched.assert_not_called()
        imported.assert_not_called()
        executed.assert_not_called()

    def test_declared_path_escape_is_refused(self) -> None:
        with self.assertRaises(AdapterRefusal) as refusal:
            LegacyRappHubInspector().inspect(FIXTURES / "legacy_hub_escape")
        self.assertEqual(refusal.exception.code, "legacy-path-escape")


if __name__ == "__main__":
    unittest.main()
