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
from scripts.organization_seeds import SEED_SLUGS, build_all  # noqa: E402
from scripts.update_agent_lock import (  # noqa: E402
    GITHUB_SUBSCRIPTION_CONTRACT,
    SUBSCRIPTION_CONTRACT,
    digest,
)

PRODUCT_VERSION = "0.1.1"
GENERATED_AT = "2026-09-18T23:29:19Z"
CORE_CARD_ISSUED_AT = "2026-09-18T19:16:11Z"
SITE_BASE_URL = "https://kody-w.github.io/hive-hub"
API_PATH = "api/hive-hub/v1"
SAMPLE_REPOSITORY = "kody-w/hive-hub"
SAMPLE_REVISION = "8e9ee55a7eb9fe4b4aaa084290e1916c0edcade9"
SAMPLE_DECLARATION_ID = (
    "dial:sha256:a917f8e41e56639a7036109b39888ee37793b7eeb045c08e387903da5c9da1af"
)
SAMPLE_DIAL_ID = "dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32"
SAMPLE_CHANT = "juniper-quartz-harbor-birch-cobalt-nook-flint"
assert derive_chant(SAMPLE_DIAL_ID) == SAMPLE_CHANT
SOURCE_COMMITS = {
    "adapters": "243fdcbb6934f1989d1d2bd1e9a0e1ee34c5cef0",
    "core": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
    "skill": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
    "static_web": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
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
    example = source_reference("examples/hive-hub-public-lab.json")
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
            **example,
            "media_type": "application/json",
        },
    ]
    learning_body = {
        "schema": "hive-hub-learning-bundle/1",
        "artifacts": artifacts,
    }
    return {
        "schema": "hive-hub-declaration/1",
        "id": SAMPLE_DECLARATION_ID,
        "name": "Hive Hub public onboarding laboratory",
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
    relative = "skill-declarations/hive-hub-public-lab.json"
    reference = source_reference(relative)
    record = {
        "id": SAMPLE_DIAL_ID,
        "aliases": [],
        "chants": [derive_chant(SAMPLE_DIAL_ID)],
        "locator": reference["url"],
        "declaration": reference,
    }
    identity_body = {
        "chants": record["aliases"],
        "locator": record["locator"],
        "declaration": reference,
    }
    assert "dial:sha256:" + digest(identity_body) == SAMPLE_DIAL_ID
    return (
        {
            "schema": "hive-hub-dialbook/2",
            "chant": {
                "protocol": CHANT_PROTOCOL,
                "algorithm": ("sha256(utf8(full-canonical-dial-record-id))[0:7] mod 128"),
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


def build_core_card(locator: str, issued_at: str = CORE_CARD_ISSUED_AT) -> dict[str, Any]:
    body = {
        "kind": "ai-join-card-body",
        "schema_version": 1,
        "principal": {"kind": "ai", "id": "hive-hub-camera"},
        "locator": locator,
        "expected_record_id": None,
        "expected_protocol_fingerprint": None,
        "adapter_plan": None,
        "issued_at": issued_at,
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
        "issued_at": body["issued_at"],
    }


def seed_contracts(seed: dict[str, Any], *, check: bool) -> dict[str, Any]:
    slug = seed["slug"]
    protocol = source_reference("protocols/rapp-work-organization-seed-v1.json")
    conformance = source_reference("conformance/rapp-work-organization-seed-v1.json")
    seed_reference = source_reference(f"organization-seeds/{slug}.json")
    learning = {
        "schema": "hive-hub-learning-bundle/1",
        "artifacts": [
            {"role": "spec", **protocol, "media_type": "application/json"},
            {"role": "conformance", **conformance, "media_type": "application/json"},
            {"role": "examples", **seed_reference, "media_type": "application/json"},
        ],
    }
    declaration = {
        "schema": "hive-hub-declaration/1",
        "id": "dial:sha256:" + digest({"seed": seed_reference, "kind": "seed-declaration"}),
        "name": seed["name"],
        "access": {"visibility": "public", "mode": "acl-only"},
        "protocol": {
            "id": "rapp-work-sdk/1",
            "fingerprint": protocol["sha256"],
            "spec_sha256": protocol["sha256"],
        },
        "adapter": {
            "id": SUBSCRIPTION_CONTRACT["id"],
            "fingerprint": digest(SUBSCRIPTION_CONTRACT),
        },
        "learning": {**learning, "sha256": digest(learning)},
        "conformance": {
            "id": "rapp-work-organization-seed/1",
            "artifact_sha256": conformance["sha256"],
        },
        "join": {
            "kind": "subscription",
            "next_step": (
                f"Inspect the {seed['name']} seed's initialize.json, team work, and "
                "synthetic case. Use your locally trusted exact RAPP Work SDK to plan "
                "Organization and Workspace creation. Obtain approval of complete native "
                "plans and starter-file effects before setup. This subscription does not "
                "activate an organization, run downloaded code, or grant membership."
            ),
        },
        "extensions": {
            "seed": seed_reference,
            "seed_status": "seed-not-activated",
            "workspace_profile": "rapp-work-sdk/1",
            "sdk_commit": seed["dependencies"]["sdk"]["commit"],
            "authority": False,
        },
    }
    write_or_check(
        ROOT / "public-src" / "skill-declarations" / f"seed-{slug}.json",
        canonical(declaration),
        check=check,
    )
    reference = source_reference(f"skill-declarations/seed-{slug}.json")
    body = {"chants": [slug], "locator": reference["url"], "declaration": reference}
    dial_id = "dial:sha256:" + digest(body)
    dial_record = {
        "id": dial_id,
        "aliases": [slug],
        "chants": [derive_chant(dial_id)],
        "locator": reference["url"],
        "declaration": reference,
    }
    record = {
        "kind": "dial-record",
        "recordId": f"seed-{slug}",
        "displayName": seed["name"],
        "summary": seed["tagline"],
        "visibility": "public",
        "access": {
            "authorization": "existing-source-acl",
            "mode": "acl-only",
            "unreachableResponse": "Do not distinguish an absent target from an unauthorized one.",
        },
        "aliases": [slug],
        "dialId": dial_id,
        "chants": [{"role": "candidate-locator-only", "value": derive_chant(dial_id)}],
        "chantProtocolId": "hive-hub-chant-v1",
        "protocolId": "rapp-work-organization-seed-v1",
        "learningBundleId": "rapp-work-organization-seed-learning-v1",
        "conformanceId": "rapp-work-organization-seed-contract-v1",
        "adapterId": "rapp-work-organization-seed-adapter-v1",
        "claims": {"authority": [], "semanticCompatibility": []},
        "locator": {"provider": "static-seed", "seedId": f"organization-seed-{slug}"},
        "security": {
            "credentialsIncluded": False,
            "retrievedContent": "inert-until-approved-and-verified",
        },
    }
    write_or_check(
        ROOT / "public-src" / "records" / f"seed-{slug}.json",
        canonical(record),
        check=check,
    )
    write_or_check(
        ROOT / "public-src" / "cards" / f"seed-{slug}-core.json",
        canonical(build_core_card(dial_id, GENERATED_AT)),
        check=check,
    )
    return dial_record


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
    seed_records: list[dict[str, Any]],
    check: bool,
) -> None:
    target = ROOT / "public-manifest.json"
    manifest = json.loads(read_regular_bytes(target).decode("utf-8"))
    generated_kinds = {
        "core-card",
        "core-schema",
        "release",
        "skill-declaration",
        "organization-seed",
    }
    entries = [
        entry
        for entry in manifest["entries"]
        if entry["kind"] not in generated_kinds
        and entry["id"] != "hive-hub-public-lab-learning-example"
        and entry["id"] != "hive-network-global-skill"
        and entry["id"] not in {f"seed-{slug}" for slug in SEED_SLUGS}
        and not entry["id"].startswith("rapp-work-organization-seed-")
    ]
    entries.extend(
        [
            manifest_entry(
                "hive-network-global-skill", "source-archive", "skills/hive-network.json"
            ),
            manifest_entry(
                "hive-hub-release-0.1.1",
                "release",
                "release/hive-hub-0.1.1.json",
            ),
            manifest_entry(
                "hive-hub-public-lab-learning-example",
                "source-archive",
                "examples/hive-hub-public-lab.json",
            ),
            manifest_entry(
                "hive-hub-public-lab-skill-declaration",
                "skill-declaration",
                "skill-declarations/hive-hub-public-lab.json",
            ),
            manifest_entry(
                "hive-hub-public-lab-core-card",
                "core-card",
                "cards/hive-hub-public-lab-core.json",
            ),
        ]
    )
    entries.extend(
        [
            manifest_entry(
                "rapp-work-organization-seed-v1",
                "protocol",
                "protocols/rapp-work-organization-seed-v1.json",
            ),
            manifest_entry(
                "rapp-work-organization-seed-contract-v1",
                "conformance",
                "conformance/rapp-work-organization-seed-v1.json",
            ),
            manifest_entry(
                "rapp-work-organization-seed-adapter-v1",
                "adapter",
                "adapters/rapp-work-organization-seed-v1.json",
            ),
            manifest_entry(
                "rapp-work-organization-seed-learning-v1",
                "learning-bundle",
                "learning-bundles/rapp-work-organization-seed-v1.json",
            ),
        ]
    )
    for slug in SEED_SLUGS:
        entries.extend(
            [
                manifest_entry(
                    f"organization-seed-{slug}",
                    "organization-seed",
                    f"organization-seeds/{slug}.json",
                ),
                manifest_entry(f"seed-{slug}", "record", f"records/seed-{slug}.json"),
                manifest_entry(
                    f"seed-{slug}-skill-declaration",
                    "skill-declaration",
                    f"skill-declarations/seed-{slug}.json",
                ),
                manifest_entry(
                    f"seed-{slug}-core-card", "core-card", f"cards/seed-{slug}-core.json"
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
    card = next(
        item for item in manifest["cards"] if item["cardId"] == "hive-hub-public-lab-public"
    )
    card["coreCardId"] = "hive-hub-public-lab-core-card"
    card["skillDeclarationId"] = "hive-hub-public-lab-skill-declaration"
    card["skillDialId"] = skill_dial_id
    card["chant"] = derive_chant(skill_dial_id)
    manifest["cards"] = [card]
    for slug, record in zip(SEED_SLUGS, seed_records, strict=True):
        seed = json.loads(
            read_regular_bytes(ROOT / "public-src/organization-seeds" / f"{slug}.json")
        )
        manifest["cards"].append(
            {
                "cardId": f"seed-{slug}-public",
                "chant": record["chants"][0],
                "coreCardId": f"seed-{slug}-core-card",
                "recordId": f"seed-{slug}",
                "skillDeclarationId": f"seed-{slug}-skill-declaration",
                "skillDialId": record["id"],
                "slug": slug,
                "title": seed["name"],
            }
        )
    write_or_check(target, canonical(manifest), check=check)


def sync(*, check: bool) -> None:
    skill_bytes = read_regular_bytes(ROOT / "skills/hive-network/SKILL.md")
    write_or_check(
        ROOT / "public-src/skills/hive-network.json",
        canonical(
            {
                "kind": "agent-skill-document",
                "name": "hive-network",
                "mediaType": "text/markdown",
                "bytes": len(skill_bytes),
                "sha256": sha(skill_bytes),
                "content": skill_bytes.decode("utf-8"),
            }
        ),
        check=check,
    )
    seeds = build_all(root=ROOT, check=check)
    seed_records = [seed_contracts(seed, check=check) for seed in seeds]
    declaration = build_skill_declaration()
    declaration_path = ROOT / "public-src" / "skill-declarations" / "hive-hub-public-lab.json"
    write_or_check(declaration_path, canonical(declaration), check=check)

    dialbook, dial_id = build_skill_dialbook(declaration)
    dialbook["records"].extend(seed_records)
    write_or_check(
        ROOT / "skills" / "hive-hub" / "registry" / "public-dialbook.json",
        canonical(dialbook),
        check=check,
    )
    write_or_check(
        ROOT / "public-src" / "cards" / "hive-hub-public-lab-core.json",
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
                ROOT / "skills" / "hive-hub" / "schemas" / "core-ai-join-card.schema.json",
                data,
                check=check,
            )
    update_manifest(
        schema_names=schema_names,
        skill_dial_id=dial_id,
        seed_records=seed_records,
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
