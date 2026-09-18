from __future__ import annotations

from pathlib import Path
from typing import Any

from hive_hub import (
    AdapterEffect,
    AdapterPlan,
    AdapterRegistration,
    AIJoinCard,
    ConformanceContract,
    ConformanceRequirement,
    DialRecord,
    LearningArtifact,
    LearningBundle,
    Principal,
    ProtocolDeclaration,
    ProtocolFingerprint,
    canonical_bytes,
)

TARGET = Path(__file__).parent / "generic"
FIXED_TIME = "2026-09-18T19:16:11Z"


def write(name: str, value: dict[str, Any]) -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / name).write_bytes(canonical_bytes(value) + b"\n")


def main() -> None:
    conformance = ConformanceContract.create(
        version="1.0",
        requirements=[
            ConformanceRequirement("decode-envelope", "Decode a Firefly envelope."),
            ConformanceRequirement("preserve-order", "Preserve event ordering."),
        ],
    )
    declaration = ProtocolDeclaration.create(
        name="Firefly Mesh",
        protocol_version="7.2",
        media_type="application/vnd.firefly.mesh+json",
        capabilities=["discover", "join", "observe"],
        conformance_address=conformance.address,
    )
    bundle = LearningBundle.create(
        protocol_fingerprint=declaration.fingerprint,
        bundle_version="2026.09",
        summary="A protocol-neutral learning bundle for Firefly Mesh.",
        conformance_contract=conformance,
        artifacts=[
            LearningArtifact.create(
                name="examples/envelope.json",
                media_type="application/json",
                content='{"event":"glow","sequence":1}',
            ),
            LearningArtifact.create(
                name="protocol.txt",
                media_type="text/plain",
                content="Firefly Mesh documents are inert UTF-8 data.",
            ),
        ],
    )
    adapter = AdapterRegistration.create(
        protocol_fingerprint=declaration.fingerprint,
        name="Firefly local adapter",
        adapter_version="3.0",
        locator="urn:firefly:adapter:local-v3",
        conformance_address=conformance.address,
        operations=["authorize", "fetch", "subscribe"],
        effect_kinds=["fetch"],
    )
    record = DialRecord.create(
        name="Firefly Commons",
        description="A generic public Hive using the Firefly Mesh protocol.",
        visibility="public",
        protocol_fingerprint=declaration.fingerprint,
        learning_bundle_address=bundle.address,
        adapter_registration_address=adapter.address,
        urls=["https://firefly.invalid/hives/commons"],
        chants=["firefly commons"],
    )
    adapter_plan = AdapterPlan.create(
        adapter_registration_address=adapter.address,
        record_id=record.id,
        effects=[
            AdapterEffect.create(
                effect_id="fetch-public-snapshot",
                kind="fetch",
                description="Fetch only after separate adapter approval.",
                locator=record.urls[0],
            )
        ],
    )
    human_card = AIJoinCard.create(
        principal=Principal.create(kind="human", identifier="person:example"),
        locator=record.id,
        expected_record_id=record.id,
        expected_protocol_fingerprint=declaration.fingerprint,
        issued_at=FIXED_TIME,
    )
    ai_card = AIJoinCard.create(
        principal=Principal.create(kind="ai", identifier="agent:example"),
        locator=record.id,
        expected_record_id=record.id,
        expected_protocol_fingerprint=declaration.fingerprint,
        adapter_plan=adapter_plan,
        issued_at=FIXED_TIME,
    )
    write("conformance-contract.json", conformance.to_dict())
    write("protocol-declaration.json", declaration.to_dict())
    write(
        "protocol-fingerprint.json",
        ProtocolFingerprint.from_declaration(declaration).to_dict(),
    )
    write("learning-bundle.json", bundle.to_dict())
    write("adapter-registration.json", adapter.to_dict())
    write("public-dial-record.json", record.to_dict())
    write("human-join-card.json", human_card.to_dict())
    write("ai-join-card.json", ai_card.to_dict())
    write(
        "manifest.json",
        {
            "adapter_registration_address": adapter.address,
            "dial_record_id": record.id,
            "learning_bundle_address": bundle.address,
            "protocol_fingerprint": declaration.fingerprint,
        },
    )


if __name__ == "__main__":
    main()
