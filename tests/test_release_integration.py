from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from unittest import mock

from hive_hub import AIJoinCard
from hive_hub import _windows_file as windows_file
from hive_hub.adapter_runtime import builtin_adapter_contracts
from scripts import (
    build_release_manifest,
    check_public_release,
    file_integrity,
    update_agent_lock,
)
from scripts.file_integrity import FileIntegrityError

from .helpers import PROJECT_ROOT, MockWindowsFileApi, WorkspaceTestCase


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ReleaseIntegrationTests(WorkspaceTestCase):
    def test_release_posix_link_policy_still_requires_exactly_one(self) -> None:
        with mock.patch.object(file_integrity, "_is_windows", return_value=False):
            for link_count, accepted in ((0, False), (1, True), (2, False)):
                information = os.stat_result(
                    (stat.S_IFREG, 1, 1, link_count, 0, 0, 0, 0, 0, 0)
                )
                with self.subTest(link_count=link_count):
                    self.assertEqual(
                        file_integrity._has_single_file_link(
                            self.work / "file",
                            information,
                        ),
                        accepted,
                    )

    def test_release_file_link_policy_uses_true_windows_metadata(self) -> None:
        source = self.work / "source.txt"
        source.write_bytes(b"ordinary")
        for api, accepted in (
            (MockWindowsFileApi(number_of_links=1), True),
            (MockWindowsFileApi(number_of_links=2), False),
            (
                MockWindowsFileApi(
                    number_of_links=1,
                    attributes=windows_file.FILE_ATTRIBUTE_REPARSE_POINT,
                ),
                False,
            ),
            (MockWindowsFileApi(information_success=False), False),
        ):
            with (
                self.subTest(api=api, accepted=accepted),
                mock.patch.object(file_integrity, "_is_windows", return_value=True),
                mock.patch.object(windows_file, "_windows_file_api", return_value=api),
            ):
                if accepted:
                    self.assertEqual(file_integrity.read_regular_bytes(source), b"ordinary")
                else:
                    with self.assertRaises(FileIntegrityError):
                        file_integrity.read_regular_bytes(source)

    def test_release_privacy_and_package_verifiers_reject_hardlinks(self) -> None:
        source = self.work / "source.txt"
        source.write_bytes(b"same bytes")
        alias = self.work / "alias.txt"
        try:
            os.link(source, alias)
        except OSError as exc:
            self.skipTest(f"hardlinks unavailable: {exc}")
        self.assertGreaterEqual(source.stat().st_nlink, 2)

        with self.assertRaises(FileIntegrityError):
            file_integrity.read_regular_bytes(source)
        with self.assertRaises(FileIntegrityError):
            check_public_release.text(source)
        with (
            mock.patch.object(build_release_manifest, "ROOT", self.work),
            mock.patch.object(
                build_release_manifest,
                "release_paths",
                return_value=["source.txt"],
            ),
            self.assertRaises(FileIntegrityError),
        ):
            build_release_manifest.build_manifest()

        skill = self.work / "skill"
        skill.mkdir()
        package_file = skill / "package.txt"
        os.link(source, package_file)
        with (
            mock.patch.object(update_agent_lock, "SKILL", skill),
            self.assertRaises(FileIntegrityError),
        ):
            update_agent_lock.build_lock()

    def test_release_verifiers_keep_symlink_and_special_file_checks(self) -> None:
        source = self.work / "source.txt"
        source.write_bytes(b"ordinary")
        symlink = self.work / "symlink.txt"
        try:
            symlink.symlink_to(source)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(FileIntegrityError):
            file_integrity.read_regular_bytes(symlink)
        with self.assertRaises(FileIntegrityError):
            file_integrity.regular_files(self.work)

        symlink.unlink()
        special = self.work / "special"
        try:
            os.mkfifo(special)
        except (AttributeError, OSError) as exc:
            self.skipTest(f"special files unavailable: {exc}")
        with self.assertRaises(FileIntegrityError):
            file_integrity.regular_files(self.work)

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

    def test_privacy_scanner_uses_irreversible_deny_digests_only(self) -> None:
        source = (
            PROJECT_ROOT / "scripts/check_public_release.py"
        ).read_text(encoding="utf-8")
        literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        reconstructable = {
            hashlib.sha256(value.encode("utf-8")).hexdigest()
            for value in literals
        }
        reconstructable.update(
            hashlib.sha256((left + right).encode("utf-8")).hexdigest()
            for left in literals
            for right in literals
        )
        self.assertTrue(check_public_release.SAFE_DENY_DIGESTS)
        self.assertTrue(
            all(
                re.fullmatch(r"[0-9a-f]{64}", digest) is not None
                for digest in check_public_release.SAFE_DENY_DIGESTS
            )
        )
        self.assertTrue(
            check_public_release.SAFE_DENY_DIGESTS.isdisjoint(reconstructable)
        )
        private_ci_fixture = "private-ci-fixture/repository"
        injected = frozenset(
            {hashlib.sha256(private_ci_fixture.encode("utf-8")).hexdigest()}
        )
        self.assertTrue(
            check_public_release.contains_denied_identifier(
                f"https://github.com/{private_ci_fixture}",
                injected,
            )
        )
