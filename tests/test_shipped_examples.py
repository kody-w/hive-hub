from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout

from hive_hub.cli import main

from .helpers import PROJECT_ROOT, WorkspaceTestCase

EXAMPLES = PROJECT_ROOT / "examples" / "generic"


class ShippedExampleTests(WorkspaceTestCase):
    """The documented walkthrough must keep working against the shipped examples.

    Nothing else exercises examples/generic, so a release that changes an
    identity body silently rots every command in the README.
    """

    def run_cli(self, *arguments: str) -> dict:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--home", str(self.work), *arguments])
        self.assertEqual(code, 0, f"{arguments} failed: {stderr.getvalue()}")
        self.assertEqual(stderr.getvalue(), "")
        return json.loads(stdout.getvalue())

    def example(self, name: str) -> str:
        path = EXAMPLES / name
        self.assertTrue(path.is_file(), f"missing shipped example: {name}")
        return str(path)

    def test_documented_walkthrough_succeeds_on_shipped_examples(self) -> None:
        self.run_cli("validate", self.example("protocol-declaration.json"))
        self.run_cli(
            "learn",
            self.example("protocol-declaration.json"),
            self.example("learning-bundle.json"),
        )
        self.run_cli("adapter", "register", self.example("adapter-registration.json"))

        registration = self.run_cli("register", "public", self.example("public-dial-record.json"))
        self.assertTrue(registration["created"])

        manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(registration["record_id"], manifest["dial_record_id"])

        record = json.loads(
            (EXAMPLES / "public-dial-record.json").read_text(encoding="utf-8")
        )
        for chant in record["chants"]:
            dialled = self.run_cli("dial", chant, "--scope", "public")
            self.assertEqual(dialled["status"], "resolved", f"chant did not resolve: {chant}")
            self.assertEqual(dialled["record"]["id"], manifest["dial_record_id"])

        self.run_cli("inspect", manifest["protocol_fingerprint"])
        self.run_cli("subscribe", "plan", self.example("ai-join-card.json"))
        self.run_cli("index", "public")

    def test_every_shipped_example_validates(self) -> None:
        for path in sorted(EXAMPLES.glob("*.json")):
            if path.name == "manifest.json":
                continue
            with self.subTest(example=path.name):
                self.run_cli("validate", str(path))
