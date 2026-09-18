from __future__ import annotations

import json
import unittest
from collections.abc import Mapping, Sequence

from adapters.contracts import AccessOutcome, AdapterRefusal, canonical_json
from adapters.rapp import (
    RAPP_DELEGATE_RESULT_SCHEMA,
    RappDelegateCommand,
    RappDelegatingAdapter,
    RappToolKind,
)
from adapters.tests.support import fixture


class RappDelegateTests(unittest.TestCase):
    def test_delegates_read_only_envelope_without_reimplementing_authority(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        def runner(
            command: Sequence[str],
            request: bytes,
            environment: Mapping[str, str],
            timeout: float,
        ) -> tuple[int, bytes]:
            decoded = json.loads(request)
            captured.update(
                command=list(command),
                request=decoded,
                environment=dict(environment),
                timeout=timeout,
            )
            response = {
                "schema": RAPP_DELEGATE_RESULT_SCHEMA,
                "tool": "rapp-work",
                "protocol_fingerprint": "rapp-workspace/1.1#sha256:" + "a" * 64,
                "operation": "verify",
                "outcome": "reachable",
                "result": {"authority_report": "opaque-to-hive-hub"},
            }
            return 0, canonical_json(response)

        adapter = RappDelegatingAdapter(
            delegates=(
                RappDelegateCommand(
                    RappToolKind.WORK,
                    (
                        "/opt/accepted/bin/rapp-work",
                        "hive-hub-adapter",
                        "--read-only",
                        "--stdio-json",
                    ),
                ),
            ),
            runner=runner,
        )
        target = "rapp-workspace/1.1#sha256:" + "a" * 64
        result = adapter.invoke(
            tool=RappToolKind.WORK,
            operation="verify",
            protocol_fingerprint=target,
            payload={"workspace": "fixture"},
            environment={"GITHUB_TOKEN": "ambient-not-logged"},
        )
        self.assertEqual(result.outcome, AccessOutcome.REACHABLE)
        self.assertTrue(result.delegated)
        self.assertFalse(result.authority_reimplemented)
        request = captured["request"]
        assert isinstance(request, dict)
        self.assertTrue(request["read_only"])
        self.assertEqual(request["payload"], {"workspace": "fixture"})
        self.assertNotIn("ambient-not-logged", repr(result))

    def test_unavailable_delegate_remains_inert(self) -> None:
        adapter = RappDelegatingAdapter()
        result = adapter.invoke(
            tool=RappToolKind.HIVE,
            operation="inspect",
            protocol_fingerprint="rapp-hive/1#sha256:" + "b" * 64,
            payload={},
        )
        self.assertEqual(result.outcome, AccessOutcome.INERT)
        self.assertFalse(result.delegated)

    def test_generic_rapp_pipeline_is_never_discovered(self) -> None:
        seen = []

        def which(name: str) -> str | None:
            seen.append(name)
            return "/Users/example/.local/bin/rapp" if name == "rapp" else None

        adapter = RappDelegatingAdapter.discover(which=which)
        self.assertEqual(adapter.available(), ())
        self.assertEqual(seen, ["rapp-work", "rapp-hive"])

    def test_mutations_and_secret_payloads_are_refused(self) -> None:
        vectors = fixture("rapp_delegate_vectors.json")
        assert isinstance(vectors, dict)
        adapter = RappDelegatingAdapter()
        for operation in vectors["refused_operations"]:
            with (
                self.subTest(operation=operation),
                self.assertRaises(AdapterRefusal) as refusal,
            ):
                adapter.invoke(
                    tool=RappToolKind.WORK,
                    operation=operation,
                    protocol_fingerprint="rapp-workspace/1.1#sha256:" + "c" * 64,
                    payload={},
                )
            self.assertEqual(refusal.exception.code, "rapp-mutation-refused")
        with self.assertRaises(AdapterRefusal) as secret:
            adapter.invoke(
                tool=RappToolKind.HIVE,
                operation="verify",
                protocol_fingerprint="rapp-hive/1#sha256:" + "d" * 64,
                payload={"token": "must-not-cross-boundary"},
            )
        self.assertEqual(secret.exception.code, "secret-payload-refused")
        with self.assertRaises(AdapterRefusal) as invalid_protocol:
            adapter.invoke(
                tool=RappToolKind.HIVE,
                operation="verify",
                protocol_fingerprint="unknown-without-contract-digest",
                payload={},
            )
        self.assertEqual(
            invalid_protocol.exception.code,
            "invalid-protocol-fingerprint",
        )

    def test_failed_delegate_discards_output_and_stderr_semantics(self) -> None:
        adapter = RappDelegatingAdapter(
            delegates=(
                RappDelegateCommand(
                    RappToolKind.HIVE,
                    ("/opt/accepted/bin/rapp-hive",),
                ),
            ),
            runner=lambda *_args: (128, b"token=secret diagnostic"),
        )
        result = adapter.invoke(
            tool=RappToolKind.HIVE,
            operation="probe",
            protocol_fingerprint="rapp-hive/1#sha256:" + "e" * 64,
            payload={},
            environment={},
        )
        self.assertEqual(result.outcome, AccessOutcome.UNREACHABLE)
        self.assertIsNone(result.result)
        self.assertNotIn("secret diagnostic", repr(result))

    def test_secret_bearing_delegate_result_is_refused(self) -> None:
        target = "rapp-hive/1#sha256:" + "f" * 64
        response = {
            "schema": RAPP_DELEGATE_RESULT_SCHEMA,
            "tool": "rapp-hive",
            "protocol_fingerprint": target,
            "operation": "read",
            "outcome": "reachable",
            "result": {"access_token": "must-not-cross-boundary"},
        }
        adapter = RappDelegatingAdapter(
            delegates=(
                RappDelegateCommand(
                    RappToolKind.HIVE,
                    ("/opt/accepted/bin/rapp-hive",),
                ),
            ),
            runner=lambda *_args: (0, canonical_json(response)),
        )
        with self.assertRaises(AdapterRefusal) as refusal:
            adapter.invoke(
                tool=RappToolKind.HIVE,
                operation="read",
                protocol_fingerprint=target,
                payload={},
                environment={},
            )
        self.assertEqual(refusal.exception.code, "secret-result-refused")


if __name__ == "__main__":
    unittest.main()
