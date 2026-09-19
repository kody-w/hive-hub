from __future__ import annotations

import ast
import io
import json
import os
import socket
import stat
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hive_hub import ConflictError, UnsafePathError
from hive_hub import _windows_file as windows_file
from hive_hub._windows_file import WindowsFileMetadata
from hive_hub.cli import main
from hive_hub.filesystem import (
    SafeFilesystem,
    _has_single_file_link,
    read_external_file,
)

from .helpers import MockWindowsFileApi, WorkspaceTestCase, make_record, make_stack


class SafetyAndCLITests(WorkspaceTestCase):
    def test_core_posix_link_policy_still_requires_exactly_one(self) -> None:
        with patch("hive_hub.filesystem._is_windows", return_value=False):
            for link_count, accepted in ((0, False), (1, True), (2, False)):
                information = os.stat_result(
                    (stat.S_IFREG, 1, 1, link_count, 0, 0, 0, 0, 0, 0)
                )
                with self.subTest(link_count=link_count):
                    self.assertEqual(
                        _has_single_file_link(self.work / "file", -1, information),
                        accepted,
                    )

    def test_windows_path_metadata_uses_a_no_follow_handle(self) -> None:
        api = MockWindowsFileApi(number_of_links=1)
        target = self.work / "ordinary.txt"
        with patch.object(windows_file, "_windows_file_api", return_value=api):
            metadata = windows_file.windows_path_metadata(target)

        self.assertEqual(metadata.number_of_links, 1)
        self.assertFalse(metadata.is_reparse_point)
        self.assertEqual(metadata.volume_serial_number, 17)
        self.assertEqual(metadata.file_index, (1 << 32) | 2)
        self.assertEqual(api.closed_handles, [api.handle])
        self.assertEqual(len(api.create_calls), 1)
        _, desired_access, share_mode, disposition, flags = api.create_calls[0]
        self.assertEqual(desired_access, 0)
        self.assertEqual(
            share_mode,
            windows_file.FILE_SHARE_READ
            | windows_file.FILE_SHARE_WRITE
            | windows_file.FILE_SHARE_DELETE,
        )
        self.assertEqual(disposition, windows_file.OPEN_EXISTING)
        self.assertTrue(flags & windows_file.FILE_FLAG_OPEN_REPARSE_POINT)

    def test_windows_path_metadata_api_failures_fail_closed(self) -> None:
        for api in (
            MockWindowsFileApi(create_success=False),
            MockWindowsFileApi(information_success=False),
            MockWindowsFileApi(close_success=False),
        ):
            with (
                self.subTest(api=api),
                patch.object(windows_file, "_windows_file_api", return_value=api),
                self.assertRaises(OSError),
            ):
                windows_file.windows_path_metadata(self.work / "file.txt")

    def test_core_link_count_uses_true_windows_handle_metadata(self) -> None:
        target = self.work / "ordinary.txt"
        target.write_bytes(b"ordinary")
        descriptor = target.open("rb")
        self.addCleanup(descriptor.close)
        information = os.fstat(descriptor.fileno())
        with (
            patch("hive_hub.filesystem._is_windows", return_value=True),
            patch(
                "hive_hub.filesystem.windows_path_metadata",
                return_value=WindowsFileMetadata(0, 1, 17, 18),
            ),
            patch(
                "hive_hub.filesystem.windows_descriptor_metadata",
                return_value=WindowsFileMetadata(0, 1, 17, 18),
            ),
        ):
            self.assertTrue(
                _has_single_file_link(target, descriptor.fileno(), information)
            )
        with (
            patch("hive_hub.filesystem._is_windows", return_value=True),
            patch(
                "hive_hub.filesystem.windows_path_metadata",
                return_value=WindowsFileMetadata(0, 2, 17, 18),
            ),
            patch(
                "hive_hub.filesystem.windows_descriptor_metadata",
                return_value=WindowsFileMetadata(0, 2, 17, 18),
            ),
        ):
            self.assertFalse(
                _has_single_file_link(target, descriptor.fileno(), information)
            )
        with (
            patch("hive_hub.filesystem._is_windows", return_value=True),
            patch(
                "hive_hub.filesystem.windows_path_metadata",
                side_effect=OSError("GetFileInformationByHandle failed"),
            ),
        ):
            self.assertFalse(
                _has_single_file_link(target, descriptor.fileno(), information)
            )

    def test_atomic_no_replace_write_is_idempotent_and_collision_safe(self) -> None:
        filesystem = SafeFilesystem(self.work / "safe")
        first = filesystem.plan_write("documents/one.json", b'{"one":1}')
        self.assertTrue(filesystem.apply_write(first))
        self.assertFalse(filesystem.apply_write(first))
        second = filesystem.plan_write("documents/one.json", b'{"two":2}')
        with self.assertRaises(ConflictError):
            filesystem.apply_write(second)
        self.assertEqual(filesystem.read_bytes("documents/one.json"), b'{"one":1}')

    def test_symlink_inputs_and_storage_components_are_not_followed(self) -> None:
        target = self.work / "target.json"
        target.write_text('{"safe":true}', encoding="utf-8")
        link = self.work / "input-link.json"
        link.symlink_to(target)
        with self.assertRaises(UnsafePathError):
            read_external_file(link)
        parent_link = self.work / "parent-link"
        parent_link.symlink_to(self.work, target_is_directory=True)
        with self.assertRaises(UnsafePathError):
            read_external_file(parent_link / "target.json")

        root = self.work / "root"
        filesystem = SafeFilesystem(root)
        outside = self.work / "outside"
        outside.mkdir()
        (root / "records").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(UnsafePathError):
            filesystem.list_files("records")

    def test_core_flow_uses_zero_network(self) -> None:
        with (
            patch.object(socket, "socket", side_effect=AssertionError("network forbidden")),
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network forbidden"),
            ),
        ):
            stack = make_stack(self.work)
            record = make_record(stack)
            stack.hub.register_public_record(record)
            self.assertEqual(stack.hub.dial(record.id).status, "resolved")
            self.assertEqual(stack.hub.status()["network_used"], False)

    def test_source_has_no_implicit_network_or_code_execution_imports(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "hive_hub"
        source = "\n".join(path.read_text("utf-8") for path in source_root.glob("*.py"))
        forbidden = (
            "import requests",
            "import socket",
            "import subprocess",
            "os.system(",
            "eval(",
            "exec(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        for path in source_root.glob("*.py"):
            for statement in ast.parse(path.read_text("utf-8")).body:
                if isinstance(statement, ast.ImportFrom):
                    self.assertNotEqual(statement.module, "urllib.request")
                elif isinstance(statement, ast.Import):
                    self.assertNotIn("urllib.request", [alias.name for alias in statement.names])

    def test_cli_success_and_errors_are_clean_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--home", str(self.work), "status"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["kind"], "hive-hub-status")

        invalid = self.work / "duplicate.json"
        invalid.write_text('{"kind":"dial-record","kind":"other"}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--home", str(self.work), "validate", str(invalid)])
        self.assertEqual(code, 2)
        error = json.loads(stderr.getvalue())
        self.assertEqual(error["error"]["code"], "validation-error")
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_schema_inventory_is_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(["--home", str(self.work), "schema", "list"])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertIn("private-access-policy", result["schemas"])
        self.assertIn("chant-locator", result["schemas"])

    def test_cli_derives_parses_and_verifies_generic_chants(self) -> None:
        dial_id = (
            "dial:sha256:"
            "6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32"
        )
        expected = "juniper-quartz-harbor-birch-cobalt-nook-flint"
        for arguments in (
            ["chant", "derive", dial_id],
            ["chant", "parse", expected.replace("-", " ").upper()],
            ["chant", "verify", dial_id, expected],
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["--home", str(self.work), *arguments])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["chant"], expected)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(
                [
                    "--home",
                    str(self.work),
                    "chant",
                    "parse",
                    "hive-hub-public-lab",
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "validation-error")

    def test_cli_version_matches_distribution(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as exit_context, redirect_stdout(stdout):
            main(["--version"])
        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["version"], "0.1.1")
