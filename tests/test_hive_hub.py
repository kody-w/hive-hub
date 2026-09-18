"""Local-only conformance tests for the universal Hive Hub skill."""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "hive-hub"
RUNNER = SKILL / "scripts" / "run.py"
WORK = ROOT / "tests" / ".work"


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def factor(byte: int = 0x41) -> str:
    return base64.urlsafe_b64encode(bytes([byte]) * 32).rstrip(b"=").decode("ascii")


def load_runner():
    spec = importlib.util.spec_from_file_location("hive_hub_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    original_path = list(sys.path)
    original_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
        sys.dont_write_bytecode = original_bytecode
    return module


runner = load_runner()


def command(
    *arguments: str,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-B", str(RUNNER), *arguments],
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def result_of(process: subprocess.CompletedProcess[str]) -> dict:
    if process.stderr:
        raise AssertionError(f"unexpected stderr: {process.stderr}")
    return json.loads(process.stdout)


def count_key(value: object, wanted: str) -> int:
    if isinstance(value, dict):
        return sum(
            int(key == wanted) + count_key(child, wanted)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return sum(count_key(item, wanted) for item in value)
    return 0


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.lock = json.loads((SKILL / "agent.lock").read_text(encoding="utf-8"))
        self.subscription = next(
            item
            for item in self.lock["adapters"]
            if item["implementation"] == "local-subscription"
        )

    def declaration(
        self,
        path: Path,
        *,
        name: str = "Fixture Hive",
        visibility: str = "public",
        mode: str = "acl-only",
        unlock: str | None = None,
        adapter: dict | None = None,
        protocol: str = "example.protocol/1",
        next_step: str = "Read the verified welcome board.",
        extra_roles: bool = False,
        factor_scope: str = "fixture/read",
        factor_epoch: str = "1",
    ) -> dict:
        adapter = adapter or self.subscription
        spec = f"{protocol} exact specification\n".encode()
        conformance = f"{protocol} conformance\n".encode()
        artifacts = [
            {
                "role": "spec",
                "url": "https://fixtures.example/spec/v1",
                "sha256": sha(spec),
                "bytes": len(spec),
                "media_type": "text/plain",
            },
            {
                "role": "conformance",
                "url": "https://fixtures.example/conformance/v1",
                "sha256": sha(conformance),
                "bytes": len(conformance),
                "media_type": "application/json",
            },
        ]
        if extra_roles or "rapp" in protocol:
            artifacts.extend(
                [
                    {
                        "role": "schema",
                        "url": "https://fixtures.example/schema/v1",
                        "sha256": sha(b"schema"),
                        "bytes": 6,
                        "media_type": "application/json",
                    },
                    {
                        "role": "examples",
                        "url": "https://fixtures.example/examples/v1",
                        "sha256": sha(b"examples"),
                        "bytes": 8,
                        "media_type": "application/json",
                    },
                    {
                        "role": "skill",
                        "url": "https://fixtures.example/skill/v1",
                        "sha256": sha(b"skill"),
                        "bytes": 5,
                        "media_type": "text/markdown",
                    },
                ]
            )
        learning_body = {
            "schema": "hive-hub-learning-bundle/1",
            "artifacts": artifacts,
        }
        record_id = "dial:sha256:" + digest(
            {"fixture": name, "protocol": protocol, "path": path.name}
        )
        access: dict[str, object] = {
            "visibility": visibility,
            "mode": mode,
        }
        if mode == "acl+qr":
            assert unlock is not None
            access.update(
                {
                    "scope": factor_scope,
                    "epoch": factor_epoch,
                    "qr_commitment": runner.qr_commitment(
                        record_id=record_id,
                        scope=factor_scope,
                        epoch=factor_epoch,
                        fragment=unlock,
                    ),
                }
            )
        declaration = {
            "schema": "hive-hub-declaration/1",
            "id": record_id,
            "name": name,
            "access": access,
            "protocol": {
                "id": protocol,
                "fingerprint": sha(spec),
                "spec_sha256": sha(spec),
            },
            "adapter": {
                "id": adapter["id"],
                "fingerprint": adapter["fingerprint"],
            },
            "learning": {
                **learning_body,
                "sha256": digest(learning_body),
            },
            "conformance": {
                "id": "example.conformance/1",
                "artifact_sha256": sha(conformance),
            },
            "join": {
                "kind": "subscription",
                "next_step": next_step,
            },
        }
        path.mkdir(parents=True, exist_ok=True)
        (path / "hive.json").write_text(
            json.dumps(declaration, indent=2) + "\n",
            encoding="utf-8",
        )
        return declaration

    def dialbook(self, path: Path, records: list[dict]) -> list[str]:
        ids = []
        complete = []
        for record in records:
            value = dict(record)
            value["id"] = "dial:sha256:" + digest(record)
            ids.append(value["id"])
            complete.append(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"schema": "hive-hub-dialbook/1", "records": complete},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ids

    def git_repository(
        self,
        name: str,
        declaration: dict,
        *,
        branch: str = "feature/history",
        extra_files: dict[str, bytes] | None = None,
    ) -> tuple[Path, str, str]:
        source = self.root / f"{name}-source"
        remote = self.root / f"{name}.git"
        source.mkdir(parents=True)
        self._git("init", "-q", "-b", "main", str(source), cwd=self.root)
        self._git("-C", str(source), "config", "core.autocrlf", "false", cwd=self.root)
        target = source / ".well-known" / "hive.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(declaration, indent=2) + "\n", encoding="utf-8")
        for relative, data in sorted((extra_files or {}).items()):
            extra = source / relative
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(data)
        self._git("-C", str(source), "add", ".", cwd=self.root)
        self._commit(source, "main declaration")
        main_oid = self._output("-C", str(source), "rev-parse", "HEAD")
        self._git("-C", str(source), "switch", "-q", "-c", branch, cwd=self.root)
        (source / "historical.txt").write_text("preserved\n", encoding="utf-8")
        self._git("-C", str(source), "add", "historical.txt", cwd=self.root)
        self._commit(source, "historical branch")
        source_oid = self._output("-C", str(source), "rev-parse", "HEAD")
        self._git("-C", str(source), "switch", "-q", "main", cwd=self.root)
        self._git(
            "clone",
            "-q",
            "--bare",
            "--no-local",
            str(source),
            str(remote),
            cwd=self.root,
        )
        return remote, main_oid, source_oid

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_AUTHOR_NAME": "Hive Hub Fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                "GIT_COMMITTER_NAME": "Hive Hub Fixture",
                "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                "GIT_AUTHOR_DATE": "2026-09-18T12:00:00Z",
                "GIT_COMMITTER_DATE": "2026-09-18T12:00:00Z",
            }
        )
        return environment

    def _git(self, *arguments: str, cwd: Path) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            env=self._environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
        )

    def _commit(self, path: Path, message: str) -> None:
        self._git("-C", str(path), "commit", "-q", "-m", message, cwd=self.root)

    def _output(self, *arguments: str) -> str:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=self.root,
            env=self._environment(),
            text=True,
        ).strip()


class HiveHubTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = WORK / self._testMethodName
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)
        self.fixture = Fixture(self.work)

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    def test_standard_six_field_skill_triggers_and_locked_stdlib_runner(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        block = text.split("---\n", 2)[1]
        fields = {
            line.split(":", 1)[0]
            for line in block.splitlines()
            if line and not line.startswith(" ")
        }
        self.assertEqual(
            fields,
            {
                "name",
                "description",
                "license",
                "compatibility",
                "metadata",
                "allowed-tools",
            },
        )
        lowered = text.lower()
        for phrase in (
            "dial this hive",
            "join this hive on this device and tell me when you are ready",
            "camera",
            "qr",
        ):
            self.assertIn(phrase, lowered)
        verified = result_of(command("verify"))
        self.assertEqual(verified["status"], "verified")
        self.assertTrue(verified["isolated"])
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(imported.issubset(sys.stdlib_module_names | {"__future__"}))

    def test_core_camera_ai_card_dials_and_joins_through_skill(self) -> None:
        hive = self.work / "camera-card-hive"
        self.fixture.declaration(hive, name="Camera Card Hive")
        issued_at = "2026-09-18T19:37:51Z"
        body = {
            "kind": "ai-join-card-body",
            "schema_version": 1,
            "principal": {"kind": "ai", "id": "camera:fixture"},
            "locator": str(hive),
            "expected_record_id": None,
            "expected_protocol_fingerprint": None,
            "adapter_plan": None,
            "issued_at": issued_at,
        }
        card = {
            "kind": "ai-join-card",
            "schema_version": 1,
            "card_id": "urn:hivehub:sha256:" + digest(body),
            "principal": body["principal"],
            "locator": body["locator"],
            "expected_record_id": None,
            "expected_protocol_fingerprint": None,
            "adapter_plan": None,
            "issued_at": issued_at,
        }
        encoded = json.dumps(card, separators=(",", ":"))
        decoded = result_of(command("decode", "--card-json", encoded))
        self.assertEqual(decoded["card_source"], "core-ai-join-card")
        device = self.work / "camera-device"
        planned = result_of(
            command(
                "join",
                "--card-json",
                encoded,
                "--device-root",
                str(device),
            )
        )
        self.assertEqual(planned["plan"]["intent"], "save-subscription")
        ready = result_of(
            command(
                "join",
                "--card-json",
                encoded,
                "--device-root",
                str(device),
                "--apply",
                planned["plan_digest"],
            )
        )
        self.assertTrue(ready["ready"])
        self.assertTrue((device / "subscriptions").is_dir())

    def test_published_camera_card_uses_locked_public_declaration(self) -> None:
        encoded = (
            ROOT
            / "public-src"
            / "cards"
            / "softwarecoellc-vteam-hive-core.json"
        ).read_text(encoding="utf-8")
        decoded = result_of(command("decode", "--card-json", encoded))
        self.assertEqual(decoded["card_source"], "core-ai-join-card")
        self.assertEqual(decoded["locator"]["kind"], "dial-id")
        planned = result_of(
            command(
                "dial",
                "--card-json",
                encoded,
                "--device-root",
                str(self.work / "published-card-device"),
            )
        )
        self.assertEqual(planned["plan"]["intent"], "resolve-hive")
        self.assertEqual(planned["plan"]["effects"][0]["transport"], "pinned-static-json")

    def test_human_non_rapp_ai_and_camera_qr_bootstrap_decode(self) -> None:
        human = result_of(
            command(
                "decode",
                "--locator",
                "https://github.com/Example/Hive/tree/feature/camera",
            )
        )
        self.assertEqual(human["locator"]["repository"], "example/hive")
        self.assertEqual(human["locator"]["branch"], "feature/camera")
        ai_card = (ROOT / "tests" / "fixtures" / "ai-join-card.json").read_text()
        ai = result_of(command("decode", "--card-json", ai_card))
        self.assertEqual(ai["card_source"], "card-json")
        secret = factor(0x43)
        payload = json.dumps(
            {
                "schema": "hive-hub-qr-join-card/1",
                "locator": (
                    "hive://join?locator=example%2Fhive%20at%20main#"
                    + secret
                ),
            }
        )
        qr_process = command("decode", "--card-stdin", input_text=payload)
        qr = result_of(qr_process)
        self.assertTrue(qr["has_optional_factor"])
        self.assertNotIn(secret, qr_process.stdout)

    def test_generic_local_join_is_plan_first_and_workspace_is_optional(self) -> None:
        hive = self.work / "Hive Folder"
        self.fixture.declaration(hive)
        workspace = self.work / "Workspace Folder"
        workspace.mkdir()
        device = self.work / "Device State"
        planned = result_of(
            command(
                "join",
                "--locator",
                str(hive),
                "--workspace-address",
                str(workspace),
                "--device-root",
                str(device),
            )
        )
        self.assertEqual(planned["status"], "planned")
        self.assertFalse(device.exists())
        ready = result_of(
            command(
                "join",
                "--locator",
                str(hive),
                "--workspace-address",
                str(workspace),
                "--device-root",
                str(device),
                "--apply",
                planned["plan_digest"],
            )
        )
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["adapter"], "hive-hub.subscription/1")
        subscriptions = list((device / "subscriptions").glob("*.json"))
        self.assertEqual(len(subscriptions), 1)
        saved = json.loads(subscriptions[0].read_text())
        self.assertEqual(saved["workspace"]["path"], str(workspace))

    def test_unknown_protocol_returns_one_content_addressed_learning_blocker(self) -> None:
        hive = self.work / "unknown"
        unknown = {
            "id": "other.adapter/1",
            "fingerprint": "a" * 64,
            "implementation": "unavailable",
        }
        declaration = self.fixture.declaration(hive, adapter=unknown)
        process = command(
            "join",
            "--locator",
            str(hive),
            "--device-root",
            str(self.work / "device"),
        )
        value = result_of(process)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(value["blocker"]["code"], "contract-unknown")
        self.assertEqual(count_key(value, "blocker"), 1)
        learning = value["learning_bundle"]
        body = {
            "schema": learning["schema"],
            "artifacts": learning["artifacts"],
        }
        self.assertEqual(learning["sha256"], digest(body))
        self.assertEqual(learning, declaration["learning"])
        self.assertFalse((self.work / "device").exists())

    def test_rapp_declarations_require_the_full_pinned_teaching_bundle(self) -> None:
        hive = self.work / "rapp"
        complete = self.fixture.declaration(
            hive,
            protocol="rapp-hive/1",
            extra_roles=True,
        )
        validated = runner.validate_declaration(
            complete,
            limits=self.fixture.lock["limits"],
        )
        self.assertEqual(
            {item["role"] for item in validated["learning"]["artifacts"]},
            {"spec", "schema", "examples", "conformance", "skill"},
        )
        incomplete = json.loads(json.dumps(complete))
        incomplete["learning"]["artifacts"] = [
            item
            for item in incomplete["learning"]["artifacts"]
            if item["role"] != "skill"
        ]
        body = {
            "schema": incomplete["learning"]["schema"],
            "artifacts": incomplete["learning"]["artifacts"],
        }
        incomplete["learning"]["sha256"] = digest(body)
        with self.assertRaises(runner.ContractError):
            runner.validate_declaration(
                incomplete,
                limits=self.fixture.lock["limits"],
            )

    def test_static_json_fetch_is_bounded_and_hash_pinned(self) -> None:
        hive = self.work / "static"
        declaration = self.fixture.declaration(hive)
        raw = canonical(declaration)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, maximum: int) -> bytes:
                self.maximum = maximum
                return raw

            def geturl(self) -> str:
                return reference["url"]

        response = Response()
        opener = mock.Mock()
        opener.open.return_value = response
        reference = {
            "url": "https://kody-w.github.io/fixtures/hive.json",
            "sha256": sha(raw),
            "bytes": len(raw),
        }
        public_dns = [
            (
                runner.socket.AF_INET,
                runner.socket.SOCK_STREAM,
                runner.socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]
        with (
            mock.patch.object(runner.socket, "getaddrinfo", return_value=public_dns),
            mock.patch.object(
                runner,
                "build_opener",
                return_value=opener,
            ) as build_opener,
        ):
            loaded, loaded_raw = runner._fetch_pinned_json(
                reference,
                lock=self.fixture.lock,
                timeout=5,
            )
        self.assertEqual(loaded, declaration)
        self.assertEqual(loaded_raw, raw)
        self.assertEqual(response.maximum, len(raw) + 1)
        handlers = build_opener.call_args.args
        pinned = [item for item in handlers if isinstance(item, runner._PinnedHTTPSHandler)]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]._approved_addresses, ("93.184.216.34",))
        changed = dict(reference)
        changed["sha256"] = "0" * 64
        with (
            mock.patch.object(runner.socket, "getaddrinfo", return_value=public_dns),
            mock.patch.object(runner, "build_opener", return_value=opener),
            self.assertRaises(runner.ContractError),
        ):
            runner._fetch_pinned_json(
                changed,
                lock=self.fixture.lock,
                timeout=5,
            )

    def test_static_resolution_plan_binds_reference_root_and_locator(self) -> None:
        locator = "dial:sha256:" + "a" * 64
        first_reference = {
            "url": "https://kody-w.github.io/hive-hub/first.json",
            "sha256": "1" * 64,
            "bytes": 101,
        }
        second_reference = {
            **first_reference,
            "url": "https://kody-w.github.io/hive-hub/second.json",
            "sha256": "2" * 64,
            "bytes": 202,
        }

        def card(reference: dict[str, object]) -> str:
            return json.dumps(
                {
                    "schema": "hive-hub-ai-join-card/1",
                    "locator": locator,
                    "declaration": reference,
                }
            )

        first_root = self.work / "first-device"
        second_root = self.work / "second-device"
        first = result_of(
            command(
                "join",
                "--card-json",
                card(first_reference),
                "--device-root",
                str(first_root),
            )
        )
        substituted = result_of(
            command(
                "join",
                "--card-json",
                card(second_reference),
                "--device-root",
                str(first_root),
                "--apply",
                first["plan_digest"],
            )
        )
        moved = result_of(
            command(
                "join",
                "--card-json",
                card(first_reference),
                "--device-root",
                str(second_root),
            )
        )
        context = first["plan"]["approval_context"]
        self.assertEqual(context["locator"], {"kind": "dial-id", "value": locator})
        self.assertEqual(context["static_declaration"], first_reference)
        self.assertEqual(
            context["output_root"]["path_sha256"],
            sha(os.fsencode(first_root)),
        )
        self.assertNotEqual(first["plan_digest"], moved["plan_digest"])
        self.assertEqual(substituted["blocker"]["code"], "plan-approval-invalid")
        self.assertFalse(first_root.exists())
        self.assertFalse(second_root.exists())

    def test_static_fetch_refuses_untrusted_ssrf_dns_and_redirects(self) -> None:
        raw = canonical(self.fixture.declaration(self.work / "ssrf"))
        base = {
            "url": "https://kody-w.github.io/hive-hub/declaration.json",
            "sha256": sha(raw),
            "bytes": len(raw),
        }
        opener = mock.Mock()
        private_dns = [
            (
                runner.socket.AF_INET,
                runner.socket.SOCK_STREAM,
                runner.socket.IPPROTO_TCP,
                "",
                ("169.254.169.254", 443),
            )
        ]
        with (
            mock.patch.object(runner.socket, "getaddrinfo", return_value=private_dns),
            mock.patch.object(runner, "build_opener", return_value=opener),
            self.assertRaises(runner.ContractError),
        ):
            runner._fetch_pinned_json(base, lock=self.fixture.lock, timeout=5)
        opener.assert_not_called()

        untrusted = {**base, "url": "https://attacker.example/declaration.json"}
        with (
            mock.patch.object(runner.socket, "getaddrinfo") as dns,
            mock.patch.object(runner, "build_opener", return_value=opener),
            self.assertRaises(runner.InputError),
        ):
            runner._fetch_pinned_json(untrusted, lock=self.fixture.lock, timeout=5)
        dns.assert_not_called()

        class RedirectedResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def geturl(self) -> str:
                return "https://kody-w.github.io/hive-hub/substitute.json"

            def read(self, maximum: int) -> bytes:
                raise AssertionError("redirected response bytes must not be read")

        public_dns = [
            (
                runner.socket.AF_INET,
                runner.socket.SOCK_STREAM,
                runner.socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]
        redirecting = mock.Mock()
        redirecting.open.return_value = RedirectedResponse()
        with (
            mock.patch.object(runner.socket, "getaddrinfo", return_value=public_dns),
            mock.patch.object(runner, "build_opener", return_value=redirecting),
            self.assertRaises(runner.ContractError),
        ):
            runner._fetch_pinned_json(base, lock=self.fixture.lock, timeout=5)

    def test_chant_collision_never_guesses_and_full_dial_id_resolves(self) -> None:
        first = self.work / "first"
        second = self.work / "second"
        self.fixture.declaration(first, name="First Hive")
        self.fixture.declaration(second, name="Second Hive")
        chant = "ember hollow quartz tidal vessel marrow lantern"
        records = [
            {"chants": [chant], "locator": str(first)},
            {"chants": [chant], "locator": str(second)},
        ]
        dialbook = self.work / "dialbook.json"
        ids = self.fixture.dialbook(dialbook, records)
        collision = result_of(
            command(
                "join",
                "--locator",
                chant,
                "--dialbook",
                str(dialbook),
            )
        )
        self.assertEqual(collision["blocker"]["code"], "chant-collision")
        self.assertEqual(collision["blocker"]["details"]["candidate_ids"], sorted(ids))
        exact = result_of(
            command(
                "join",
                "--locator",
                ids[0],
                "--dialbook",
                str(dialbook),
                "--device-root",
                str(self.work / "device"),
            )
        )
        self.assertEqual(exact["status"], "planned")

    def test_optional_qr_factor_is_after_access_and_never_persisted(self) -> None:
        secret = factor(0x52)
        hive = self.work / "factor"
        self.fixture.declaration(
            hive,
            visibility="private",
            mode="acl+qr",
            unlock=secret,
        )
        device = self.work / "device"
        missing = result_of(
            command(
                "join",
                "--locator",
                str(hive),
                "--device-root",
                str(device),
            )
        )
        self.assertEqual(missing["blocker"]["code"], "second-factor-required")
        self.assertFalse(device.exists())
        card = json.dumps(
            {
                "schema": "hive-hub-qr-join-card/1",
                "locator": str(hive),
                "unlock_fragment": secret,
            }
        )
        planned_process = command(
            "join",
            "--card-stdin",
            "--device-root",
            str(device),
            input_text=card,
        )
        planned = result_of(planned_process)
        self.assertNotIn(secret, planned_process.stdout)
        ready_process = command(
            "join",
            "--card-stdin",
            "--device-root",
            str(device),
            "--apply",
            planned["plan_digest"],
            input_text=card,
        )
        ready = result_of(ready_process)
        self.assertTrue(ready["ready"])
        self.assertNotIn(secret, ready_process.stdout)
        persisted = b"".join(
            path.read_bytes() for path in device.rglob("*") if path.is_file()
        )
        self.assertNotIn(secret.encode(), persisted)

    def test_qr_factor_rejects_weak_unbound_and_wrong_record_values(self) -> None:
        with self.assertRaises(runner.FactorError):
            runner.decode_qr_factor("weak-factor")
        self.assertEqual(
            runner.qr_commitment(
                record_id="urn:hivehub:sha256:" + "a" * 64,
                scope="scope",
                epoch="1",
                fragment=factor(),
            ),
            "urn:hivehub:sha256:"
            "8ff1a706e0443a239d3c148fb4d7531f5bff6d472f0b466e03c1ca15dfa59856",
        )

        secret = factor(0x51)
        declaration = self.fixture.declaration(
            self.work / "bound-factor",
            visibility="private",
            mode="acl+qr",
            unlock=secret,
            factor_scope="vault/read",
            factor_epoch="2026-q3",
        )
        legacy = json.loads(json.dumps(declaration))
        legacy["access"] = {
            "visibility": "private",
            "mode": "acl+qr",
            "unlock_sha256": sha(secret.encode("ascii")),
        }
        with self.assertRaises(runner.ContractError):
            runner.validate_declaration(legacy, limits=self.fixture.lock["limits"])

        wrong_record = json.loads(json.dumps(declaration))
        wrong_record["id"] = "dial:sha256:" + "f" * 64
        with self.assertRaises(runner.FactorError):
            runner._check_factor(wrong_record, secret)

        hmac_compare = __import__("hmac").compare_digest
        with mock.patch.object(runner.hmac, "compare_digest", wraps=hmac_compare) as compare:
            runner._check_factor(declaration, secret)
            self.assertTrue(compare.called)

    def test_public_and_private_github_repositories_use_native_existing_access(self) -> None:
        for visibility in ("public", "private"):
            with self.subTest(visibility=visibility):
                hive = self.work / f"{visibility}-declaration"
                declaration = self.fixture.declaration(
                    hive,
                    name=f"{visibility.title()} Fixture",
                    visibility=visibility,
                )
                remote, _, _ = self.fixture.git_repository(
                    visibility,
                    declaration,
                )
                device = self.work / f"{visibility}-device"
                env = os.environ.copy()
                env.update(
                    {
                        "HIVE_HUB_LOCAL_TESTING": "1",
                        "HIVE_HUB_TEST_GIT_REMOTE": str(remote),
                    }
                )
                locator = f"example/{visibility}-hive at feature/history"
                first = result_of(
                    command(
                        "join",
                        "--locator",
                        locator,
                        "--device-root",
                        str(device),
                        env=env,
                    )
                )
                self.assertEqual(first["plan"]["intent"], "resolve-hive")
                second = result_of(
                    command(
                        "join",
                        "--locator",
                        locator,
                        "--device-root",
                        str(device),
                        "--apply",
                        first["plan_digest"],
                        env=env,
                    )
                )
                self.assertEqual(second["plan"]["intent"], "save-subscription")
                third = result_of(
                    command(
                        "join",
                        "--locator",
                        locator,
                        "--device-root",
                        str(device),
                        "--apply",
                        second["plan_digest"],
                        env=env,
                    )
                )
                self.assertTrue(third["ready"])

    def test_unauthorized_and_nonexistent_remote_results_are_identical(self) -> None:
        outputs = []
        for name in ("not-a-repository", "also-not-a-repository"):
            fake = self.work / name
            fake.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "HIVE_HUB_LOCAL_TESTING": "1",
                    "HIVE_HUB_TEST_GIT_REMOTE": str(fake),
                }
            )
            device = self.work / f"device-{name}"
            plan = result_of(
                command(
                    "join",
                    "--locator",
                    "example/hidden at main",
                    "--device-root",
                    str(device),
                    env=env,
                )
            )
            result = result_of(
                command(
                    "join",
                    "--locator",
                    "example/hidden at main",
                    "--device-root",
                    str(device),
                    "--apply",
                    plan["plan_digest"],
                    env=env,
                )
            )
            outputs.append(result)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["blocker"]["code"], "target-unreachable")
        self.assertEqual(count_key(outputs[0], "blocker"), 1)

    def test_copycat_repository_contract_never_executes_repository_code(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("Git is unavailable")
        declaration_path = self.work / "copycat-declaration"
        declaration = self.fixture.declaration(
            declaration_path,
            name="Copycat Contract Hive",
        )
        execution_marker = self.work / "repository-code-executed"
        network_marker = self.work / "repository-network-attempted"
        malicious = (
            "from pathlib import Path\n"
            f"Path({str(execution_marker)!r}).write_text('executed')\n"
            f"Path({str(network_marker)!r}).write_text('network')\n"
            "import socket\n"
            "socket.create_connection(('127.0.0.1', 9), timeout=0.1)\n"
        ).encode()
        remote, _, _ = self.fixture.git_repository(
            "copycat",
            declaration,
            extra_files={
                "join-contract.json": canonical(
                    {
                        "schema": "copyable-self-authored-contract/1",
                        "command": ["python3", "-B", "microsol.py", "setup"],
                    }
                ),
                "microsol.py": malicious,
                "setup.py": malicious,
                "verify.py": malicious,
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "HIVE_HUB_LOCAL_TESTING": "1",
                "HIVE_HUB_TEST_GIT_REMOTE": str(remote),
            }
        )
        device = self.work / "copycat-device"
        locator = "fixture-org/copycat at feature/history"
        resolve_plan = result_of(
            command(
                "join",
                "--locator",
                locator,
                "--device-root",
                str(device),
                env=env,
            )
        )
        self.assertFalse(execution_marker.exists())
        self.assertFalse(network_marker.exists())
        join_plan = result_of(
            command(
                "join",
                "--locator",
                locator,
                "--device-root",
                str(device),
                "--apply",
                resolve_plan["plan_digest"],
                env=env,
            )
        )
        self.assertEqual(join_plan["plan"]["intent"], "save-subscription")
        self.assertEqual(join_plan["plan"]["adapter_plan"]["kind"], "adapter-plan")
        self.assertEqual(join_plan["plan"]["adapter_plan"]["effects"], [])
        self.assertFalse(execution_marker.exists())
        self.assertFalse(network_marker.exists())
        ready_process = command(
            "join",
            "--locator",
            locator,
            "--device-root",
            str(device),
            "--apply",
            join_plan["plan_digest"],
            env=env,
        )
        ready = result_of(ready_process)
        self.assertEqual(ready_process.returncode, 0)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["adapter_plan"], join_plan["plan"]["adapter_plan"])
        self.assertEqual(ready["adapter_effects_status"], "not-executed")
        self.assertFalse(execution_marker.exists())
        self.assertFalse(network_marker.exists())

    def test_credentials_and_unlocks_never_reach_output(self) -> None:
        credential = "credential-fixture-value"
        process = command(
            "join",
            "--locator",
            f"https://user:{credential}@github.com/example/hive",
        )
        value = result_of(process)
        self.assertEqual(value["blocker"]["code"], "input-invalid")
        self.assertNotIn(credential, process.stdout + process.stderr)
        card = json.dumps(
            {
                "schema": "hive-hub-join-card/1",
                "locator": "example/hive at main",
                "unlock_fragment": "must-not-be-on-command-line",
            }
        )
        unsafe = command("decode", "--card-json", card)
        self.assertEqual(result_of(unsafe)["blocker"]["code"], "input-invalid")
        self.assertNotIn("must-not-be-on-command-line", unsafe.stdout)

    def test_cross_platform_storage_parts_and_paths_with_spaces(self) -> None:
        windows = PureWindowsPath("C:/Device/Ada") / ".agent-storage" / "hive-hub" / "v1"
        self.assertEqual(
            windows.as_posix(),
            "C:/Device/Ada/.agent-storage/hive-hub/v1",
        )
        home = self.work / "Home With Spaces"
        self.assertEqual(
            runner.default_device_root(home),
            home / ".agent-storage" / "hive-hub" / "v1",
        )
        hive = self.work / "Path With Spaces" / "Hive"
        self.fixture.declaration(hive)
        decoded = result_of(command("decode", "--locator", str(hive)))
        self.assertEqual(decoded["locator"]["kind"], "local")

    def test_every_refusal_has_exactly_one_blocker(self) -> None:
        cases = [
            command("join", "--locator", "not a locator"),
            command("join", "--locator", "https://github.com/example/repo#fragment"),
            command("decode", "--locator", "one two three"),
        ]
        for process in cases:
            with self.subTest(output=process.stdout):
                value = result_of(process)
                self.assertEqual(count_key(value, "blocker"), 1)
                self.assertFalse(value["ready"])

    def test_downloaded_or_declared_commands_remain_inert(self) -> None:
        marker = self.work / "must-not-exist"
        hive = self.work / "inert"
        declaration = self.fixture.declaration(
            hive,
            next_step=f"python3 -c 'open({str(marker)!r}, \"w\").write(\"bad\")'",
        )
        planned = result_of(
            command(
                "dial",
                "--locator",
                str(hive),
                "--device-root",
                str(self.work / "device"),
            )
        )
        ready = result_of(
            command(
                "dial",
                "--locator",
                str(hive),
                "--device-root",
                str(self.work / "device"),
                "--apply",
                planned["plan_digest"],
            )
        )
        self.assertEqual(ready["user_summary"]["next_step"], declaration["join"]["next_step"])
        self.assertTrue(ready["user_summary"]["text_is_inert"])
        self.assertFalse(marker.exists())

    def test_copied_skill_folder_operates_without_repository_context(self) -> None:
        copied = self.work / "Copied Skill With Spaces"
        shutil.copytree(SKILL, copied)
        verify = subprocess.run(
            [sys.executable, "-I", "-B", str(copied / "scripts" / "run.py"), "verify"],
            cwd=self.work,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result_of(verify)["status"], "verified")
        decoded = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(copied / "scripts" / "run.py"),
                "decode",
                "--locator",
                "example/hive at main",
            ],
            cwd=self.work,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result_of(decoded)["status"], "decoded")


if __name__ == "__main__":
    unittest.main()
