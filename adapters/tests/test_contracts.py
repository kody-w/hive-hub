from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from adapters.contracts import (
    AdapterRefusal,
    ProtocolFingerprint,
    RequirementLevel,
)
from adapters.defaults import build_default_registry
from adapters.rapp import RappDelegatingAdapter
from adapters.registry import InertProtocolAdapter


class ContractTests(unittest.TestCase):
    def test_all_six_adapters_declare_complete_exact_contracts(self) -> None:
        registry = build_default_registry(rapp_adapter=RappDelegatingAdapter())
        declarations = registry.declarations()
        self.assertEqual(len(declarations), 6)
        self.assertEqual(len({item.fingerprint.value for item in declarations}), 6)
        root = Path(__file__).resolve().parents[2]
        for declaration in declarations:
            self.assertTrue(declaration.capabilities)
            self.assertTrue(declaration.private_access_modes)
            self.assertTrue(declaration.learning_bundle.documents)
            self.assertTrue(declaration.conformance.fixtures)
            self.assertTrue(declaration.conformance.assertions)
            self.assertTrue(declaration.authority_model)
            for fixture_path in declaration.conformance.fixtures:
                self.assertTrue((root / fixture_path).exists(), fixture_path)
            self.assertTrue(
                any(
                    requirement.capability == "remote-write"
                    and requirement.level is RequirementLevel.FORBIDDEN
                    for requirement in declaration.capabilities
                )
            )
            for document in declaration.learning_bundle.documents:
                self.assertFalse(document.executable)
                self.assertEqual(
                    hashlib.sha256(document.content.encode("utf-8")).hexdigest(),
                    document.sha256,
                )
            self.assertEqual(
                ProtocolFingerprint.parse(declaration.fingerprint.value),
                declaration.fingerprint,
            )

    def test_unknown_protocol_is_inert_and_never_falls_back_to_rapp(self) -> None:
        calls = []

        def runner(*args: object) -> tuple[int, bytes]:
            calls.append(args)
            return 0, b"{}"

        rapp = RappDelegatingAdapter(runner=runner)
        registry = build_default_registry(rapp_adapter=rapp)
        unknown = registry.resolve("unknown-hive/9#sha256:" + "a" * 64)
        self.assertIsInstance(unknown, InertProtocolAdapter)
        assert isinstance(unknown, InertProtocolAdapter)
        self.assertFalse(unknown.fallback_used)
        with self.assertRaises(AdapterRefusal) as refusal:
            unknown.invoke()
        self.assertEqual(refusal.exception.code, "unsupported-protocol")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
