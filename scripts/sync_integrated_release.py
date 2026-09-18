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

from hive_hub import __version__ as CORE_VERSION  # noqa: E402
from hive_hub.adapter_runtime import builtin_adapter_contracts  # noqa: E402
from scripts.file_integrity import FileIntegrityError, read_regular_bytes  # noqa: E402
from scripts.update_agent_lock import (  # noqa: E402
    GITHUB_SUBSCRIPTION_CONTRACT,
    digest,
)

PRODUCT_VERSION = "0.1.0"
GENERATED_AT = "2026-09-18T19:16:11Z"
SITE_BASE_URL = "https://kody-w.github.io/hive-hub"
API_PATH = "api/hive-hub/v1"
SAMPLE_REPOSITORY = "billwhalenmsft/softwarecoellc-vteam-hive"
SAMPLE_REVISION = "f66da3d879b53a439bc87de764d79f68ceec048a"
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
    record = source_reference("records/softwarecoellc-vteam-hive.json")
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
    identity = {
        "repository": SAMPLE_REPOSITORY,
        "revision": SAMPLE_REVISION,
        "protocol_sha256": protocol["sha256"],
        "adapter_sha256": digest(GITHUB_SUBSCRIPTION_CONTRACT),
    }
    return {
        "schema": "hive-hub-declaration/1",
        "id": "dial:sha256:" + digest(identity),
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
    body = {
        "chants": [],
        "locator": reference["url"],
        "declaration": reference,
    }
    record_id = "dial:sha256:" + digest(body)
    return (
        {
            "schema": "hive-hub-dialbook/1",
            "records": [{"id": record_id, **body}],
        },
        record_id,
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
        "issued_at": GENERATED_AT,
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
        "issued_at": GENERATED_AT,
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
        "publicSample": {
            "repository": SAMPLE_REPOSITORY,
            "revision": SAMPLE_REVISION,
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
        "hive-hub-release-0.1.0",
        "softwarecoellc-vteam-hive-skill-declaration",
        "softwarecoellc-vteam-hive-core-card",
        *(f"core-schema-{name}" for name in schema_names),
    }
    entries = [
        entry for entry in manifest["entries"] if entry["id"] not in generated_ids
    ]
    entries.extend(
        [
            manifest_entry(
                "hive-hub-release-0.1.0",
                "release",
                "release/hive-hub-0.1.0.json",
            ),
            manifest_entry(
                "softwarecoellc-vteam-hive-skill-declaration",
                "skill-declaration",
                "skill-declarations/softwarecoellc-vteam-hive.json",
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
    card = manifest["cards"][0]
    card["coreCardId"] = "softwarecoellc-vteam-hive-core-card"
    card["skillDeclarationId"] = "softwarecoellc-vteam-hive-skill-declaration"
    card["skillDialId"] = skill_dial_id
    write_or_check(target, canonical(manifest), check=check)


def sync(*, check: bool) -> None:
    declaration = build_skill_declaration()
    declaration_path = (
        ROOT / "public-src" / "skill-declarations" / "softwarecoellc-vteam-hive.json"
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
        ROOT / "public-src" / "release" / "hive-hub-0.1.0.json",
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
