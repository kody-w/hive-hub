#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hive_hub.canonical import canonical_bytes, canonical_dumps, loads_json  # noqa: E402
from hive_hub.contracts import (  # noqa: E402
    AdapterRegistration,
    ConformanceContract,
    ConformanceRequirement,
    DialRecord,
    LearningArtifact,
    LearningBundle,
    ProtocolDeclaration,
)
from hive_hub.errors import ValidationError  # noqa: E402
from hive_hub.limits import MAX_JSON_BYTES  # noqa: E402


def locator_urls(value: dict[str, Any]) -> list[str]:
    urls = []
    for key, child in value.items():
        if isinstance(child, dict):
            urls.extend(locator_urls(child))
        elif isinstance(child, str) and (key == "url" or key.endswith("Url")):
            urls.append(child)
    return urls


def project(value: dict[str, Any]) -> dict[str, Any]:
    record = value["record"]
    protocol = value["protocol"]
    learning = value["learningBundle"]
    adapter = value["adapter"]
    conformance = ConformanceContract.create(
        version=value["conformance"]["version"],
        requirements=[
            ConformanceRequirement(item["id"], item["rule"])
            for item in value["conformance"]["requirements"]
        ],
    )
    declaration = ProtocolDeclaration.create(
        name=protocol.get("protocolName", protocol["protocolId"]),
        protocol_version=protocol["version"],
        media_type=protocol.get("mediaTypes", ["application/json"])[0],
        capabilities=["inspect"],
        conformance_address=conformance.address,
    )
    artifacts = [
        LearningArtifact.create(
            name=name + ".json",
            media_type="application/json",
            content=(canonical_bytes(document) + b"\n").decode("utf-8"),
        )
        for name, document in (
            ("adapter", adapter),
            ("conformance", value["conformance"]),
            ("learning-bundle", learning),
            ("locator", record["locator"]),
            ("protocol", protocol),
        )
    ]
    bundle = LearningBundle.create(
        protocol_fingerprint=declaration.fingerprint,
        bundle_version=learning["version"],
        summary="Inert published discovery contracts; no adapter execution is authorized.",
        conformance_contract=conformance,
        artifacts=artifacts,
    )
    registration = AdapterRegistration.create(
        protocol_fingerprint=declaration.fingerprint,
        name=adapter["adapterId"],
        adapter_version=adapter["version"],
        locator=record["adapter"]["url"],
        conformance_address=conformance.address,
        operations=["inspect"],
    )
    core = DialRecord.create(
        name=record["displayName"],
        description=record["summary"],
        visibility="public",
        protocol_fingerprint=declaration.fingerprint,
        learning_bundle_address=bundle.address,
        adapter_registration_address=registration.address,
        urls=locator_urls(record["locator"]),
        # Derived locators cannot be part of the body from which they are derived.
        chants=[],
    )
    return {
        "coreRecord": core.to_dict(),
        "coreContracts": {
            "protocol": declaration.to_dict(),
            "learningBundle": bundle.to_dict(),
            "adapter": registration.to_dict(),
        },
    }


def main() -> None:
    value = loads_json(sys.stdin.buffer.read(MAX_JSON_BYTES + 1))
    if not isinstance(value, dict):
        raise ValidationError("public projection input must be an object")
    print(canonical_dumps(project(value)))


if __name__ == "__main__":
    main()
