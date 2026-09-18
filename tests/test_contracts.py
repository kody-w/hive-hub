from __future__ import annotations

import hashlib
import importlib.resources
import json

from hive_hub import (
    CHANT_PROTOCOL,
    CHANT_VOCABULARY,
    CHANT_VOCABULARY_SHA256,
    AIJoinCard,
    ChantLocator,
    DialRecord,
    LearningArtifact,
    LimitError,
    Principal,
    ProtocolFingerprint,
    ValidationError,
    canonical_bytes,
    chant_contract,
    content_address,
    derive_chant,
    generate_qr_fragment,
    get_schema,
    loads_json,
    normalize_chant,
    schema_names,
)

from .helpers import FIXED_TIME, WorkspaceTestCase, make_record, make_stack


class CanonicalContractTests(WorkspaceTestCase):
    SAMPLE_DIAL_ID = (
        "dial:sha256:"
        "6efe6390f51f67d1bca0169280ed8e091040563430186df4bb28ebff4298486c"
    )
    SAMPLE_CHANT = "jetty-gorse-grove-pond-marrow-otter-weir"

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

    def test_protocol_neutral_chant_derives_from_the_full_dial_id(self) -> None:
        self.assertEqual(CHANT_PROTOCOL, "hive-hub-chant/1")
        self.assertEqual(len(CHANT_VOCABULARY), 128)
        self.assertEqual(
            hashlib.sha256("\n".join(CHANT_VOCABULARY).encode("utf-8")).hexdigest(),
            CHANT_VOCABULARY_SHA256,
        )
        self.assertEqual(derive_chant(self.SAMPLE_DIAL_ID), self.SAMPLE_CHANT)
        self.assertEqual(
            normalize_chant("  JETTY GORSE GROVE POND MARROW OTTER WEIR  "),
            self.SAMPLE_CHANT,
        )
        locator = ChantLocator.create(self.SAMPLE_DIAL_ID)
        self.assertEqual(ChantLocator.from_dict(locator.to_dict()), locator)
        contract = chant_contract()
        self.assertFalse(contract["requires_rapp_identity"])
        self.assertFalse(contract["requires_rapp_runtime"])
        self.assertTrue(contract["full_dial_id_verification_required"])
        with self.assertRaisesRegex(ValidationError, "seven words"):
            normalize_chant("softwarecoellc-vteam-hive")

    def test_dial_record_v1_identity_and_legacy_chants_remain_stable(self) -> None:
        stack = make_stack(self.work)
        record = make_record(stack)
        self.assertEqual(record.chants, ("firefly commons",))
        self.assertEqual(DialRecord.from_dict(record.to_dict()), record)

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
            locator=self.SAMPLE_CHANT,
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
            "chant-locator",
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
