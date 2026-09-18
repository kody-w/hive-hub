#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from hive_hub import (  # noqa: E402
    CHANT_ADDRESS_BITS,
    CHANT_PROTOCOL,
    CHANT_VOCABULARY_PROVENANCE,
    CHANT_VOCABULARY_SHA256,
    derive_chant,
)
from hive_hub import __version__ as CORE_VERSION  # noqa: E402
from hive_hub.adapter_runtime import builtin_adapter_contracts  # noqa: E402
from scripts.file_integrity import FileIntegrityError, read_regular_bytes  # noqa: E402
from scripts.update_agent_lock import (  # noqa: E402
    GITHUB_SUBSCRIPTION_CONTRACT,
    digest,
)

PRODUCT_VERSION = "0.1.1"
GENERATED_AT = "2026-09-18T22:02:35Z"
CORE_CARD_ISSUED_AT = "2026-09-18T19:16:11Z"
SITE_BASE_URL = "https://kody-w.github.io/hive-hub"
API_PATH = "api/hive-hub/v1"
SAMPLE_REPOSITORY = "billwhalenmsft/softwarecoellc-vteam-hive"
SAMPLE_REVISION = "f66da3d879b53a439bc87de764d79f68ceec048a"
SAMPLE_DIAL_ID = (
    "dial:sha256:"
    "6efe6390f51f67d1bca0169280ed8e091040563430186df4bb28ebff4298486c"
)
SAMPLE_CHANT = "jetty-gorse-grove-pond-marrow-otter-weir"
assert derive_chant(SAMPLE_DIAL_ID) == SAMPLE_CHANT
SOURCE_COMMITS = {
    "adapters": "243fdcbb6934f1989d1d2bd1e9a0e1ee34c5cef0",
    "core": "dcbd22cb31f7f94e379799d7990b79ed6a71a222",
    "skill": "95021bf27a868fd5e3a14b03094b4939be1add42",
    "static_web": "b7ceeca7f9e0719faeffc23186cad90e0bf26c5f",
}


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_or_check(path: Path, data: bytes, *, check: bool) -> None:
    if check:
        try:
            current = read_regular_bytes(path)
        except FileIntegrityError:
            current = None
        if current != data:
            raise SystemExit(f"out of date: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        read_regular_bytes(path)
    path.write_bytes(data)


def source_reference(relative: str) -> dict[str, Any]:
    path = ROOT / "public-src" / relative
    data = canonical(json.loads(read_regular_bytes(path).decode("utf-8")))
    return {
        "url": f"{SITE_BASE_URL}/{API_PATH}/source/{relative}",
        "sha256": sha(data),
        "bytes": len(data),
    }


def build_skill_declaration() -> dict[str, Any]:
    protocol = source_reference("protocols/github-repository-v1.json")
    conformance = source_reference("conformance/github-repository-locator-v1.json")
    record = source_reference("records/softwarecoellc-vteam-hive-chant-v1.json")
    artifacts = [
        {
            "role": "spec",
            **protocol,
            "media_type": "application/json",
        },
        {
            "role": "conformance",
            **conformance,
            "media_type": "application/json",
        },
        {
            "role": "examples",
            **record,
            "media_type": "application/json",
        },
    ]
    learning_body = {
        "schema": "hive-hub-learning-bundle/1",
        "artifacts": artifacts,
    }
    return {
        "schema": "hive-hub-declaration/1",
        "id": SAMPLE_DIAL_ID,
        "name": "SoftwareCo LLC V-Team Hive repository example",
        "access": {"visibility": "public", "mode": "acl-only"},
        "protocol": {
            "id": "github-repository/1",
            "fingerprint": protocol["sha256"],
            "spec_sha256": protocol["sha256"],
        },
        "adapter": {
            "id": GITHUB_SUBSCRIPTION_CONTRACT["id"],
            "fingerprint": digest(GITHUB_SUBSCRIPTION_CONTRACT),
        },
        "learning": {
            **learning_body,
            "sha256": digest(learning_body),
        },
        "conformance": {
            "id": "github-repository-conformance/1",
            "artifact_sha256": conformance["sha256"],
        },
        "join": {
            "kind": "subscription",
            "next_step": (
                "Inspect the exact public repository revision while keeping all "
                "retrieved content inert until separately approved."
            ),
        },
        "extensions": {
            "repository": SAMPLE_REPOSITORY,
            "revision": SAMPLE_REVISION,
            "authority": False,
        },
    }


def build_skill_dialbook(declaration: dict[str, Any]) -> tuple[dict[str, Any], str]:
    relative = "skill-declarations/softwarecoellc-vteam-hive.json"
    reference = source_reference(relative)
    record = {
        "id": SAMPLE_DIAL_ID,
        "aliases": [],
        "chants": [derive_chant(SAMPLE_DIAL_ID)],
        "locator": reference["url"],
        "declaration": reference,
    }
    return (
        {
            "schema": "hive-hub-dialbook/2",
            "chant": {
                "protocol": CHANT_PROTOCOL,
                "algorithm": (
                    "sha256(utf8(full-canonical-dial-record-id))[0:7] mod 128"
                ),
                "address_bits": CHANT_ADDRESS_BITS,
                "vocabulary_sha256": CHANT_VOCABULARY_SHA256,
                "vocabulary_provenance": CHANT_VOCABULARY_PROVENANCE,
                "candidate_locator_only": True,
                "full_dial_id_verification_required": True,
                "requires_rapp_identity": False,
                "requires_rapp_runtime": False,
            },
            "records": [record],
        },
        SAMPLE_DIAL_ID,
    )


def build_core_card(locator: str) -> dict[str, Any]:
    body = {
        "kind": "ai-join-card-body",
        "schema_version": 1,
        "principal": {"kind": "ai", "id": "hive-hub-camera"},
        "locator": locator,
        "expected_record_id": None,
        "expected_protocol_fingerprint": None,
        "adapter_plan": None,
        "issued_at": CORE_CARD_ISSUED_AT,
    }
    return {
        "kind": "ai-join-card",
        "schema_version": 1,
        "card_id": "urn:hivehub:sha256:" + digest(body),
        "principal": body["principal"],
        "locator": locator,
        "expected_record_id": None,
        "expected_protocol_fingerprint": None,
        "adapter_plan": None,
        "issued_at": CORE_CARD_ISSUED_AT,
    }


def build_release() -> dict[str, Any]:
    adapters = [item.summary() for item in builtin_adapter_contracts()]
    return {
        "kind": "hive-hub-release",
        "schemaVersion": 1,
        "version": PRODUCT_VERSION,
        "sourceCommits": SOURCE_COMMITS,
        "core": {
            "distribution": "hive-hub",
            "import": "hive_hub",
            "version": CORE_VERSION,
            "runtimeDependencies": [],
            "schemaPath": f"/{API_PATH}/core-schemas/",
        },
        "adapters": {
            "package": "adapters",
            "optional": True,
            "runtimeDependencies": [],
            "contracts": adapters,
        },
        "skill": {
            "name": "hive-hub",
            "path": "skills/hive-hub",
            "version": PRODUCT_VERSION,
            "acceptsCoreAiJoinCard": True,
            "cameraCardPath": f"/{API_PATH}/cards/core/",
        },
        "static": {
            "apiPath": f"/{API_PATH}/",
            "pagesPath": "/hub/",
            "publicInputsOnly": True,
            "apiContractVersion": "1.0.0",
        },
        "chant": {
            "protocol": CHANT_PROTOCOL,
            "addressBits": CHANT_ADDRESS_BITS,
            "vocabularySha256": CHANT_VOCABULARY_SHA256,
            "vocabularyProvenance": CHANT_VOCABULARY_PROVENANCE,
            "requiresRappIdentity": False,
            "requiresRappRuntime": False,
            "candidateLocatorOnly": True,
            "fullDialIdVerificationRequired": True,
        },
        "publicSample": {
            "repository": SAMPLE_REPOSITORY,
            "revision": SAMPLE_REVISION,
            "dialId": SAMPLE_DIAL_ID,
            "chant": SAMPLE_CHANT,
        },
    }


def manifest_entry(entry_id: str, kind: str, path: str) -> dict[str, Any]:
    return {
        "classification": "public",
        "id": entry_id,
        "kind": kind,
        "path": path,
        "sha256": sha(read_regular_bytes(ROOT / "public-src" / path)),
    }


def update_manifest(
    *,
    schema_names: list[str],
    skill_dial_id: str,
    check: bool,
) -> None:
    target = ROOT / "public-manifest.json"
    manifest = json.loads(read_regular_bytes(target).decode("utf-8"))
    generated_ids = {
        "hive-hub-release-0.1.1",
        "hive-hub-release-0.1.0",
        "historical-source-release-0.1.0",
        "historical-source-record-softwarecoellc",
        "historical-source-declaration-softwarecoellc",
        "hive-hub-chant-v1",
        "historical-card-4a9d98ad",
        "historical-core-card-6d991eea",
        "historical-declaration-afab2137",
        "historical-record-8a91f582",
        "historical-release-04a4eee6",
        "historical-receipt-ba52e736",
        "publish-softwarecoellc-example-0002",
        "softwarecoellc-vteam-hive-skill-declaration",
        "softwarecoellc-vteam-hive-core-card",
        "softwarecoellc-vteam-hive-main-f66da3d",
        *(f"core-schema-{name}" for name in schema_names),
    }
    entries = [
        entry for entry in manifest["entries"] if entry["id"] not in generated_ids
    ]
    entries.extend(
        [
            manifest_entry(
                "hive-hub-release-0.1.1",
                "release",
                "release/hive-hub-0.1.1.json",
            ),
            manifest_entry(
                "historical-source-release-0.1.0",
                "source-archive",
                "release/hive-hub-0.1.0.json",
            ),
            manifest_entry(
                "historical-source-record-softwarecoellc",
                "source-archive",
                "records/softwarecoellc-vteam-hive.json",
            ),
            manifest_entry(
                "historical-source-declaration-softwarecoellc",
                "source-archive",
                "skill-declarations/softwarecoellc-vteam-hive.json",
            ),
            manifest_entry(
                "softwarecoellc-vteam-hive-main-f66da3d",
                "record",
                "records/softwarecoellc-vteam-hive-chant-v1.json",
            ),
            manifest_entry(
                "hive-hub-chant-v1",
                "protocol",
                "protocols/hive-hub-chant-v1.json",
            ),
            manifest_entry(
                "historical-receipt-ba52e736",
                "historical-receipt",
                (
                    "receipts/history/"
                    "ba52e73692f991d5a495087cc6f7ef2984299dfe6b940f92b0d88b3f11c81951.json"
                ),
            ),
            manifest_entry(
                "historical-card-4a9d98ad",
                "historical-object",
                (
                    "history/cards/"
                    "4a9d98adfd98118a5f7b458d3af41340944f8eb957ef1990f6f96a402f20d700.json"
                ),
            ),
            manifest_entry(
                "historical-core-card-6d991eea",
                "historical-object",
                (
                    "history/cards/"
                    "6d991eeaea3fe68e34d060176390f71d1672fd469e91e2fa9b7c9c0e904b4c29.json"
                ),
            ),
            manifest_entry(
                "historical-declaration-afab2137",
                "historical-object",
                (
                    "history/declarations/"
                    "afab2137c0dfd3ddba6ab59257cb364c8585a51d7492c2c291b1d10688d9c75c.json"
                ),
            ),
            manifest_entry(
                "historical-record-8a91f582",
                "historical-object",
                (
                    "history/records/"
                    "8a91f5821d2663ea6e106d9e1dea1c04238159a48a8f4f814f67d6f05662d1cd.json"
                ),
            ),
            manifest_entry(
                "historical-release-04a4eee6",
                "historical-object",
                (
                    "history/releases/"
                    "04a4eee6ac2b2b13924828ab1be868557f61053012d7e586dad97f97ed7f5d15.json"
                ),
            ),
            manifest_entry(
                "publish-softwarecoellc-example-0002",
                "receipt",
                "receipts/0002-correct-softwarecoellc-chant.json",
            ),
            manifest_entry(
                "softwarecoellc-vteam-hive-skill-declaration",
                "skill-declaration",
                "skill-declarations/softwarecoellc-vteam-hive-chant-v1.json",
            ),
            manifest_entry(
                "softwarecoellc-vteam-hive-core-card",
                "core-card",
                "cards/softwarecoellc-vteam-hive-core.json",
            ),
        ]
    )
    entries.extend(
        manifest_entry(
            f"core-schema-{name}",
            "core-schema",
            f"core-schemas/{name}.schema.json",
        )
        for name in schema_names
    )
    manifest["entries"] = sorted(entries, key=lambda item: item["id"])
    manifest["productVersion"] = PRODUCT_VERSION
    manifest["build"]["generatedAt"] = GENERATED_AT
    card = manifest["cards"][0]
    card["coreCardId"] = "softwarecoellc-vteam-hive-core-card"
    card["skillDeclarationId"] = "softwarecoellc-vteam-hive-skill-declaration"
    card["skillDialId"] = skill_dial_id
    card["chant"] = derive_chant(skill_dial_id)
    write_or_check(target, canonical(manifest), check=check)


def sync(*, check: bool) -> None:
    declaration = build_skill_declaration()
    declaration_path = (
        ROOT
        / "public-src"
        / "skill-declarations"
        / "softwarecoellc-vteam-hive-chant-v1.json"
    )
    write_or_check(declaration_path, canonical(declaration), check=check)

    dialbook, dial_id = build_skill_dialbook(declaration)
    write_or_check(
        ROOT / "skills" / "hive-hub" / "registry" / "public-dialbook.json",
        canonical(dialbook),
        check=check,
    )
    write_or_check(
        ROOT / "public-src" / "cards" / "softwarecoellc-vteam-hive-core.json",
        canonical(build_core_card(dial_id)),
        check=check,
    )
    write_or_check(
        ROOT / "public-src" / "release" / "hive-hub-0.1.1.json",
        canonical(build_release()),
        check=check,
    )
    integrated_adapters = {
        "schema": "hive-hub-integrated-adapters/1",
        "version": PRODUCT_VERSION,
        "adapters": [item.summary() for item in builtin_adapter_contracts()],
    }
    write_or_check(
        ROOT / "skills" / "hive-hub" / "registry" / "integrated-adapters.json",
        canonical(integrated_adapters),
        check=check,
    )

    schema_source = ROOT / "src" / "hive_hub" / "schema"
    schema_target = ROOT / "public-src" / "core-schemas"
    schema_names: list[str] = []
    for source in sorted(schema_source.glob("*.schema.json")):
        name = source.name.removesuffix(".schema.json")
        schema_names.append(name)
        data = read_regular_bytes(source)
        write_or_check(schema_target / source.name, data, check=check)
        if source.name == "ai-join-card.schema.json":
            write_or_check(
                ROOT
                / "skills"
                / "hive-hub"
                / "schemas"
                / "core-ai-join-card.schema.json",
                data,
                check=check,
            )
    update_manifest(
        schema_names=schema_names,
        skill_dial_id=dial_id,
        check=check,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    sync(check=args.check)
    message = (
        "integrated release contracts are current"
        if args.check
        else "synced integrated release contracts"
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
