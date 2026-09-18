from __future__ import annotations

import hashlib
import importlib.resources
import json

from hive_hub import (
    AIJoinCard,
    DialRecord,
    LearningArtifact,
    LimitError,
    Principal,
    ProtocolFingerprint,
    ValidationError,
    canonical_bytes,
    content_address,
    generate_qr_fragment,
    get_schema,
    loads_json,
    schema_names,
)

from .helpers import FIXED_TIME, WorkspaceTestCase, make_record, make_stack


class CanonicalContractTests(WorkspaceTestCase):
    def test_canonical_bytes_and_generic_content_address_are_deterministic(self) -> None:
        left = canonical_bytes({"z": [3, 2, 1], "a": "glow"})
        right = canonical_bytes({"a": "glow", "z": [3, 2, 1]})
        self.assertEqual(left, b'{"a":"glow","z":[3,2,1]}')
        self.assertEqual(left, right)
        self.assertEqual(
            content_address({"z": [3, 2, 1], "a": "glow"}),
            "urn:hivehub:sha256:" + hashlib.sha256(left).hexdigest(),
        )

    def test_duplicate_keys_and_floats_are_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
            loads_json('{"same":1,"same":2}')
        with self.assertRaisesRegex(ValidationError, "floating-point"):
            loads_json('{"imprecise":1.25}')
        with self.assertRaisesRegex(LimitError, "64-bit"):
            loads_json('{"huge":100000000000000000000000000000000000000}')

    def test_learning_artifacts_allow_bounded_multiline_text(self) -> None:
        artifact = LearningArtifact.create(
            name="protocol.md",
            media_type="text/markdown",
            content="# Protocol\n\n1. Decode.\n2. Validate.\n",
        )
        self.assertIn("\n", artifact.content)

    def test_closed_contract_refuses_unknown_fields_and_tampering(self) -> None:
        stack = make_stack(self.work)
        record = make_record(stack)
        unknown = record.to_dict()
        unknown["qr_fragment"] = "forbidden"
        with self.assertRaisesRegex(ValidationError, "unknown fields"):
            DialRecord.from_dict(unknown)
        tampered = record.to_dict()
        tampered["name"] = "Changed after addressing"
        with self.assertRaisesRegex(ValidationError, "does not match"):
            DialRecord.from_dict(tampered)

    def test_protocol_fingerprint_is_the_declaration_address(self) -> None:
        stack = make_stack(self.work)
        fingerprint = ProtocolFingerprint.from_declaration(stack.declaration)
        self.assertEqual(fingerprint.algorithm, "sha256")
        self.assertEqual(fingerprint.value, stack.declaration.fingerprint)
        self.assertEqual(
            ProtocolFingerprint.from_dict(fingerprint.to_dict()),
            fingerprint,
        )

    def test_join_card_cannot_carry_url_fragment_or_extra_qr_field(self) -> None:
        principal = Principal.create(kind="ai", identifier="agent:firefly")
        with self.assertRaisesRegex(ValidationError, "URL fragment"):
            AIJoinCard.create(
                principal=principal,
                locator="https://firefly.invalid/hive#factor",
                issued_at=FIXED_TIME,
            )
        valid = AIJoinCard.create(
            principal=principal,
            locator="firefly commons",
            issued_at=FIXED_TIME,
        ).to_dict()
        valid["qr_fragment"] = "not-a-contract-field"
        with self.assertRaisesRegex(ValidationError, "unknown fields"):
            AIJoinCard.from_dict(valid)

    def test_qr_factor_and_credential_query_cannot_be_locators(self) -> None:
        principal = Principal.create(kind="human", identifier="person:ada")
        with self.assertRaisesRegex(ValidationError, "bare QR factor"):
            AIJoinCard.create(
                principal=principal,
                locator=generate_qr_fragment(),
                issued_at=FIXED_TIME,
            )
        with self.assertRaisesRegex(ValidationError, "credential query"):
            AIJoinCard.create(
                principal=principal,
                locator="https://firefly.invalid/hive?access_token=secret",
                issued_at=FIXED_TIME,
            )

    def test_all_published_schemas_are_closed_and_packaged(self) -> None:
        package_root = importlib.resources.files("hive_hub")
        required = {
            "dial-record",
            "protocol-declaration",
            "protocol-fingerprint",
            "learning-bundle",
            "adapter-registration",
            "adapter-registration-receipt",
            "local-subscription",
            "ai-join-card",
            "bootstrap-result",
            "public-dialbook-index",
            "private-dialbook-index",
            "private-access-policy",
        }
        self.assertTrue(required.issubset(schema_names()))
        for name in schema_names():
            schema = get_schema(name)
            self.assertFalse(schema["additionalProperties"], name)
            data = (package_root / "schema" / f"{name}.schema.json").read_text("utf-8")
            self.assertEqual(json.loads(data), schema)
