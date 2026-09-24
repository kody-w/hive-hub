from __future__ import annotations

import ast
import copy
import hashlib
import json
import unittest
from typing import Any
from unittest.mock import patch

from adapters.contracts import AdapterRefusal, ProtocolFingerprint, RequirementLevel
from adapters.defaults import build_default_registry
from adapters.hive_md import (
    CHECKER_PATH,
    CHECKER_SHA256,
    CONVENTION_COMMIT,
    CONVENTION_SPEC_SHA256,
    HIVE_MD_DECLARATION,
    HIVE_MD_PROTOCOL,
    BrainstemHandoff,
    HiveMdDialPinAdapter,
    HiveMdDialPins,
    parse_dial_pins,
    parse_dial_pins_artifact,
)
from adapters.rapp import RappDelegatingAdapter
from adapters.registry import AdapterRegistry, InertProtocolAdapter
from adapters.tests.support import ADAPTERS_ROOT, fixture


def vectors() -> dict[str, Any]:
    value = fixture("hive_md_vectors.json")
    assert isinstance(value, dict)
    return value


def contoso_document() -> dict[str, Any]:
    return copy.deepcopy(vectors()["valid"][0]["pins"])


def contoso_pins() -> HiveMdDialPins:
    return parse_dial_pins(contoso_document())


class HiveMdDeclarationTests(unittest.TestCase):
    def test_declaration_is_exact_complete_and_inert(self) -> None:
        declaration = HIVE_MD_DECLARATION
        self.assertEqual(declaration.fingerprint.protocol, HIVE_MD_PROTOCOL)
        self.assertEqual(
            ProtocolFingerprint.parse(declaration.fingerprint.value),
            declaration.fingerprint,
        )
        forbidden = {
            item.capability
            for item in declaration.capabilities
            if item.level is RequirementLevel.FORBIDDEN
        }
        self.assertLessEqual(
            {
                "credential-broker",
                "hive-agent-execution",
                "hive-write",
                "network-access",
                "remote-write",
            },
            forbidden,
        )
        for fixture_path in declaration.conformance.fixtures:
            self.assertTrue((ADAPTERS_ROOT.parent / fixture_path).is_file(), fixture_path)
        (document,) = declaration.learning_bundle.documents
        self.assertFalse(document.executable)
        self.assertEqual(
            hashlib.sha256(document.content.encode("utf-8")).hexdigest(),
            declaration.fingerprint.contract_sha256,
        )
        contract = json.loads(document.content)
        self.assertEqual(contract["status"], "experimental")
        self.assertEqual(contract["convention"]["commit"], CONVENTION_COMMIT)
        self.assertEqual(contract["convention"]["spec"]["sha256"], CONVENTION_SPEC_SHA256)
        self.assertEqual(contract["convention"]["checker"]["path"], CHECKER_PATH)
        self.assertEqual(contract["convention"]["checker"]["sha256"], CHECKER_SHA256)
        self.assertFalse(contract["network"] or contract["hive_writes"] or contract["executes"])

    def test_experimental_adapter_is_opt_in_and_exact(self) -> None:
        default = build_default_registry(rapp_adapter=RappDelegatingAdapter())
        self.assertNotIn(HIVE_MD_DECLARATION, default.declarations())
        registry = AdapterRegistry((HiveMdDialPinAdapter(),))
        self.assertIsInstance(
            registry.resolve(HIVE_MD_DECLARATION.fingerprint.value),
            HiveMdDialPinAdapter,
        )
        self.assertIsInstance(
            registry.resolve(f"{HIVE_MD_PROTOCOL}#sha256:" + "0" * 64),
            InertProtocolAdapter,
        )

    def test_module_cannot_reach_the_network_disk_or_processes(self) -> None:
        tree = ast.parse((ADAPTERS_ROOT / "hive_md.py").read_text(encoding="utf-8"))
        imported: set[str] = set()
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        self.assertLessEqual(
            imported,
            {
                "__future__",
                "base64",
                "binascii",
                "contracts",
                "dataclasses",
                "json",
                "re",
                "typing",
                "urllib.parse",
            },
        )
        self.assertFalse(called & {"__import__", "compile", "eval", "exec", "open"})


class HiveMdPinTests(unittest.TestCase):
    def test_valid_vectors_are_accepted_exactly(self) -> None:
        adapter = HiveMdDialPinAdapter()
        for vector in vectors()["valid"]:
            with self.subTest(vector=vector["name"]):
                pins = adapter.validate(vector["pins"])
                self.assertEqual(pins.to_document(), vector["pins"])
                self.assertEqual(pins.artifact_text(), vector["artifact"])
                self.assertEqual(adapter.validate_artifact(vector["artifact"]), pins)
                self.assertEqual(list(pins.urls), vector["urls"])
                self.assertEqual(adapter.handoff(pins).call, vector["call"])

    def test_malformed_pins_are_refused_with_exact_codes(self) -> None:
        for vector in vectors()["invalid"]:
            with self.subTest(field=vector["field"], why=vector["why"]):
                document = contoso_document()
                document[vector["field"]] = vector["value"]
                with self.assertRaises(AdapterRefusal) as refused:
                    parse_dial_pins(document)
                self.assertEqual(refused.exception.code, vector["code"])
                self.assertNotIn(vector["value"], str(refused.exception))
                fields = {key: document[key] for key in ("address", "hive", "root", "founder")}
                with self.assertRaises(AdapterRefusal) as constructed:
                    HiveMdDialPins(**fields, public_copy=document.get("public_copy"))
                self.assertEqual(constructed.exception.code, vector["code"])

    def test_required_refusal_classes_are_covered(self) -> None:
        codes = {vector["code"] for vector in vectors()["invalid"]}
        self.assertLessEqual(
            {
                "invalid-founder-fingerprint",
                "invalid-hive-address",
                "invalid-hive-id",
                "invalid-public-copy",
                "invalid-root-commit",
                "local-path-address",
                "url-credentials",
            },
            codes,
        )

    def test_malformed_shapes_are_refused(self) -> None:
        for vector in vectors()["shapes"]:
            with self.subTest(why=vector["why"]):
                document: Any = contoso_document()
                if "document" in vector:
                    document = vector["document"]
                if "remove" in vector:
                    del document[vector["remove"]]
                if "set" in vector:
                    document.update(vector["set"])
                with self.assertRaises(AdapterRefusal) as refused:
                    parse_dial_pins(document)
                self.assertEqual(refused.exception.code, vector["code"])

    def test_only_the_exact_canonical_artifact_is_accepted(self) -> None:
        for vector in vectors()["artifacts"]:
            with self.subTest(why=vector["why"]):
                with self.assertRaises(AdapterRefusal) as refused:
                    parse_dial_pins_artifact(vector["content"])
                self.assertEqual(refused.exception.code, vector["code"])
        for content in (b"{}", None, "x" * 9000):
            with self.subTest(content=type(content).__name__), self.assertRaises(AdapterRefusal):
                parse_dial_pins_artifact(content)


class HiveMdHandoffTests(unittest.TestCase):
    def test_handoff_carries_exactly_the_pins_and_hive_hub_performs_nothing(self) -> None:
        pins = contoso_pins()
        handoff = HiveMdDialPinAdapter().handoff(pins)
        document = handoff.to_dict()
        self.assertEqual(
            document["call"],
            {"action": "join", "address": pins.address, "id": pins.root},
        )
        self.assertEqual(document["compare"], {"founder": pins.founder, "hive": pins.hive})
        self.assertEqual(document["performed_by"], "person-brainstem")
        self.assertEqual(document["request"], "rapp-hive")
        self.assertEqual(document["hive_hub_effects"], [])
        self.assertEqual(document["public_copy"], pins.public_copy)
        description = handoff.description()
        for expected in (
            pins.address,
            pins.root,
            pins.hive,
            pins.founder,
            str(pins.public_copy),
            "request: rapp-hive",
            "your own Brainstem",
            "Hive Hub runs none of this",
        ):
            self.assertIn(expected, description)
        self.assertNotIn("\n", description)
        self.assertLessEqual(len(description.encode("utf-8")), 4096)

    def test_handoff_requires_validated_pins(self) -> None:
        with self.assertRaises(AdapterRefusal) as refused:
            HiveMdDialPinAdapter().handoff(contoso_document())  # type: ignore[arg-type]
        self.assertEqual(refused.exception.code, "invalid-dial-pins")
        self.assertIsInstance(BrainstemHandoff(contoso_pins()), BrainstemHandoff)

    def test_validation_and_handoff_are_offline_and_write_nothing(self) -> None:
        adapter = HiveMdDialPinAdapter()
        document = contoso_document()
        invalid = vectors()["invalid"]
        with (
            patch("builtins.open") as opened,
            patch("subprocess.run") as ran,
            patch("subprocess.Popen") as spawned,
            patch("socket.socket") as connected,
            patch("socket.getaddrinfo") as resolved,
            patch("urllib.request.urlopen") as fetched,
            patch("os.system") as shelled,
        ):
            pins = adapter.validate(document)
            adapter.validate_artifact(pins.artifact_text())
            adapter.handoff(pins).description()
            for vector in invalid:
                broken = dict(document, **{vector["field"]: vector["value"]})
                with self.assertRaises(AdapterRefusal):
                    adapter.validate(broken)
        for mock in (opened, ran, spawned, connected, resolved, fetched, shelled):
            mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
