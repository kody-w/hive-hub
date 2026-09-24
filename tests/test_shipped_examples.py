from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from types import ModuleType
from unittest import mock

from adapters.hive_md import (
    CHECKER_SHA256,
    CONVENTION_COMMIT,
    CONVENTION_SPEC_SHA256,
    HIVE_MD_FINGERPRINT,
    PINS_ARTIFACT,
    HiveMdDialPinAdapter,
)
from hive_hub import (
    ADAPTER_INTERFACE_VERSION,
    AdapterRegistration,
    AIJoinCard,
    ConformanceContract,
    DialRecord,
    LearningBundle,
    ProtocolDeclaration,
    ProtocolFingerprint,
    canonical_bytes,
    derive_chant,
)
from hive_hub.canonical import address_digest
from hive_hub.cli import main
from hive_hub.contracts import validate_record_contracts

from .helpers import PROJECT_ROOT, WorkspaceTestCase

EXAMPLES = PROJECT_ROOT / "examples" / "generic"
HIVE_MD_EXAMPLES = PROJECT_ROOT / "examples" / "hive-md"


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


# Pinned from kody-w/rapp-model-hive@2bd7c95 (example/HISTORY.md, rebuilt by its build_example.py).
CONTOSO_ROOT = "f934db89e0c73d71843d634b8ddbd53154732735"
CONTOSO_HIVE = "185d0eb5d4b1247b260042d0d840d5c3"
CONTOSO_FOUNDER = "SHA256:q18VTrWDieC+Sc25wpbcIHm4/gUotkmUJpyFgDeOdyY"


def load_hive_md_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_hive_md", PROJECT_ROOT / "examples" / "build_hive_md.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HiveMdExampleTests(WorkspaceTestCase):
    """The experimental folder-Hive example: exact protocol documents and an inert join."""

    run_cli = ShippedExampleTests.run_cli

    def document(self, name: str) -> dict:
        path = HIVE_MD_EXAMPLES / name
        data = path.read_bytes()
        value = json.loads(data)
        self.assertEqual(data, canonical_bytes(value) + b"\n", f"{name} is not canonical")
        return value

    def test_every_hive_md_document_validates(self) -> None:
        names = sorted(path.name for path in HIVE_MD_EXAMPLES.glob("*.json"))
        self.assertEqual(
            names,
            [
                "adapter-registration.json",
                "ai-join-card.json",
                "conformance-contract.json",
                "human-join-card.json",
                "learning-bundle.json",
                "manifest.json",
                "protocol-declaration.json",
                "protocol-fingerprint.json",
                "public-dial-record.json",
            ],
        )
        for name in names:
            if name != "manifest.json":
                with self.subTest(example=name):
                    self.run_cli("validate", str(HIVE_MD_EXAMPLES / name))

    def test_protocol_documents_verify_and_pin_the_convention(self) -> None:
        conformance = ConformanceContract.from_dict(self.document("conformance-contract.json"))
        declaration = ProtocolDeclaration.from_dict(self.document("protocol-declaration.json"))
        fingerprint = ProtocolFingerprint.from_dict(self.document("protocol-fingerprint.json"))
        bundle = LearningBundle.from_dict(self.document("learning-bundle.json"))
        adapter = AdapterRegistration.from_dict(self.document("adapter-registration.json"))
        record = DialRecord.from_dict(self.document("public-dial-record.json"))
        self.assertEqual((declaration.name, declaration.protocol_version), ("hive-md", "0"))
        self.assertEqual(declaration.adapter_api_version, ADAPTER_INTERFACE_VERSION)
        self.assertEqual(declaration.conformance_address, conformance.address)
        self.assertEqual(fingerprint.value, declaration.fingerprint)
        validate_record_contracts(record, declaration, bundle, adapter)
        requirements = " ".join(item.description for item in conformance.requirements)
        for pinned in (
            "agents/hive_agent.py check",
            CHECKER_SHA256,
            "HIVE-MD.md",
            CONVENTION_SPEC_SHA256,
            CONVENTION_COMMIT,
        ):
            self.assertIn(pinned, requirements)
        artifacts = {artifact.name: artifact for artifact in bundle.artifacts}
        contract_digest = HIVE_MD_FINGERPRINT.contract_sha256
        self.assertEqual(
            address_digest(artifacts["hive-md/adapter-contract.json"].content_address),
            contract_digest,
        )
        self.assertTrue(adapter.locator.endswith(f":sha256:{contract_digest}"))
        self.assertEqual(adapter.effect_kinds, ("other",))
        self.assertEqual(adapter.operations, ("handoff", "validate"))

        pins = HiveMdDialPinAdapter().validate_artifact(artifacts[PINS_ARTIFACT].content)
        self.assertEqual(
            (pins.root, pins.hive, pins.founder), (CONTOSO_ROOT, CONTOSO_HIVE, CONTOSO_FOUNDER)
        )
        self.assertTrue(pins.address.startswith("https://contoso.invalid/"))
        self.assertEqual(record.urls, pins.urls)
        vectors = json.loads(
            (PROJECT_ROOT / "adapters" / "fixtures" / "hive_md_vectors.json").read_text("utf-8")
        )
        self.assertEqual(pins.to_document(), vectors["valid"][0]["pins"])

        description = HiveMdDialPinAdapter().handoff(pins).description()
        for name in ("human-join-card.json", "ai-join-card.json"):
            card = AIJoinCard.from_dict(self.document(name))
            self.assertEqual(card.expected_record_id, record.id)
            self.assertEqual(card.expected_protocol_fingerprint, declaration.fingerprint)
            assert card.adapter_plan is not None
            self.assertEqual(card.adapter_plan.record_id, record.id)
            self.assertEqual(card.adapter_plan.adapter_registration_address, adapter.address)
            (effect,) = card.adapter_plan.effects
            self.assertEqual((effect.effect_id, effect.kind), ("brainstem-hive-join", "other"))
            self.assertEqual((effect.locator, effect.description), (pins.address, description))
            self.assertTrue(effect.requires_approval)
        manifest = self.document("manifest.json")
        self.assertEqual(manifest["dial_record_id"], record.id)
        self.assertEqual(manifest["chant"], derive_chant(record.dial_id))
        self.assertEqual(manifest["dial_pins"], pins.to_document())
        self.assertIs(manifest["live_shared_copy"], False)

    def test_join_is_a_reversible_local_subscription_that_runs_nothing(self) -> None:
        def example(name: str) -> str:
            return str(HIVE_MD_EXAMPLES / name)

        manifest = self.document("manifest.json")
        with (
            mock.patch("subprocess.Popen") as spawned,
            mock.patch("subprocess.run") as ran,
            mock.patch("socket.socket") as connected,
        ):
            self.run_cli(
                "learn", example("protocol-declaration.json"), example("learning-bundle.json")
            )
            self.run_cli("adapter", "register", example("adapter-registration.json"))
            self.run_cli("register", "public", example("public-dial-record.json"))
            for query in (manifest["chant"], manifest["dial_pins"]["address"]):
                dialled = self.run_cli("dial", query, "--scope", "public")
                self.assertEqual(dialled["status"], "resolved")
                self.assertEqual(dialled["record"]["id"], manifest["dial_record_id"])
            inspected = self.run_cli("inspect", manifest["protocol_fingerprint"])
            self.assertFalse(inspected["code_executed"])
            planned = self.run_cli("subscribe", "plan", example("ai-join-card.json"))
            self.assertEqual(planned["status"], "planned")
            (effect,) = planned["plan"]["adapter_plan"]["effects"]
            self.assertIn("your own Brainstem", effect["description"])
            self.assertIn(f"id {CONTOSO_ROOT}", effect["description"])
            applied = self.run_cli(
                "bootstrap", example("human-join-card.json"), "--scope", "public", "--apply"
            )
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(
                applied["plan"]["subscription"]["adapter_effects_status"], "not-executed"
            )
            self.assertEqual(self.run_cli("status")["counts"]["local_subscriptions"], 1)
            plan_path = self.work / "join-plan.json"
            plan_path.write_text(json.dumps(applied["plan"]), encoding="utf-8")
            reverted = self.run_cli("subscribe", "revert", str(plan_path))
            self.assertTrue(reverted["removed"])
            self.assertFalse(reverted["adapter_effects_executed"])
            self.assertEqual(self.run_cli("status")["counts"]["local_subscriptions"], 0)
        for patched in (spawned, ran, connected):
            patched.assert_not_called()

    def test_documented_walkthrough_uses_the_example_chant(self) -> None:
        spoken = self.document("manifest.json")["chant"].replace("-", " ").upper()
        readme = (PROJECT_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
        self.assertIn(f'hive-hub dial "{spoken}" --scope public', readme)

    def test_hive_md_example_is_deterministic(self) -> None:
        builder = load_hive_md_builder()
        self.assertEqual(builder.documents(), builder.documents())
        target = self.work / "hive-md"
        builder.build(target)
        built = sorted(path.name for path in target.iterdir())
        shipped = sorted(path.name for path in HIVE_MD_EXAMPLES.iterdir())
        self.assertEqual(built, shipped)
        for name in shipped:
            with self.subTest(example=name):
                self.assertEqual(
                    (target / name).read_bytes(), (HIVE_MD_EXAMPLES / name).read_bytes()
                )
