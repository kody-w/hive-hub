from __future__ import annotations

import io
import json
import socket
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hive_hub import ConflictError, UnsafePathError
from hive_hub.cli import main
from hive_hub.filesystem import SafeFilesystem, read_external_file

from .helpers import WorkspaceTestCase, make_record, make_stack


class SafetyAndCLITests(WorkspaceTestCase):
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

    def test_source_has_no_network_or_code_execution_imports(self) -> None:
        source_root = Path(__file__).parents[1] / "src" / "hive_hub"
        source = "\n".join(path.read_text("utf-8") for path in source_root.glob("*.py"))
        forbidden = (
            "import requests",
            "import socket",
            "import subprocess",
            "urllib.request",
            "os.system(",
            "eval(",
            "exec(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

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

    def test_cli_version_matches_distribution(self) -> None:
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as exit_context, redirect_stdout(stdout):
            main(["--version"])
        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["version"], "0.1.0")
