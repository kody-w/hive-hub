from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

from hive_hub import AIJoinCard
from hive_hub.adapter_runtime import builtin_adapter_contracts

from .helpers import PROJECT_ROOT, WorkspaceTestCase


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ReleaseIntegrationTests(WorkspaceTestCase):
    def test_public_camera_card_is_an_exact_core_contract(self) -> None:
        card_path = (
            PROJECT_ROOT
            / "public-src"
            / "cards"
            / "softwarecoellc-vteam-hive-core.json"
        )
        card = AIJoinCard.from_dict(json.loads(card_path.read_text(encoding="utf-8")))
        self.assertEqual(card.principal.kind, "ai")
        self.assertTrue(card.locator.startswith("dial:sha256:"))
        self.assertIsNone(card.adapter_plan)

    def test_published_and_skill_core_schema_copies_are_exact(self) -> None:
        source = PROJECT_ROOT / "src/hive_hub/schema/ai-join-card.schema.json"
        copies = (
            PROJECT_ROOT / "public-src/core-schemas/ai-join-card.schema.json",
            PROJECT_ROOT / "skills/hive-hub/schemas/core-ai-join-card.schema.json",
        )
        for copy in copies:
            self.assertEqual(copy.read_bytes(), source.read_bytes())

    def test_release_metadata_matches_integrated_adapter_contracts(self) -> None:
        release = json.loads(
            (
                PROJECT_ROOT
                / "public-src"
                / "release"
                / "hive-hub-0.1.0.json"
            ).read_text(encoding="utf-8")
        )
        expected = [item.summary() for item in builtin_adapter_contracts()]
        self.assertEqual(release["version"], "0.1.0")
        self.assertTrue(release["adapters"]["optional"])
        self.assertEqual(release["adapters"]["contracts"], expected)

    def test_locked_public_dialbook_is_content_addressed(self) -> None:
        dialbook = json.loads(
            (
                PROJECT_ROOT
                / "skills"
                / "hive-hub"
                / "registry"
                / "public-dialbook.json"
            ).read_text(encoding="utf-8")
        )
        record = dialbook["records"][0]
        body = {key: value for key, value in record.items() if key != "id"}
        expected = "dial:sha256:" + hashlib.sha256(canonical(body)).hexdigest()
        self.assertEqual(record["id"], expected)

    def test_importing_core_does_not_import_adapter_package(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import sys; import hive_hub; "
                    "assert not any(name == 'adapters' or "
                    "name.startswith('adapters.') for name in sys.modules)"
                ),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
