#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.file_integrity import FileIntegrityError, read_regular_bytes  # noqa: E402

TARGET = ROOT / "release" / "release-manifest.json"
VERSION = "0.1.1"
SOURCE_COMMITS = {
    "adapters": "243fdcbb6934f1989d1d2bd1e9a0e1ee34c5cef0",
    "core": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
    "skill": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
    "static_web": "be580c9b0a8a0a46d8be2b4d0c59dda983835ba7",
}
EXCLUDED = {
    "release/release-manifest.json",
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


def release_paths() -> list[str]:
    output = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        text=True,
    )
    return sorted(
        path
        for path in output.splitlines()
        if path and path not in EXCLUDED
    )


def build_manifest() -> dict[str, object]:
    files = []
    for relative in release_paths():
        data = read_regular_bytes(ROOT / relative)
        files.append(
            {
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    inventory_root = hashlib.sha256(canonical(files)).hexdigest()
    return {
        "schema": "hive-hub-release-manifest/1",
        "version": VERSION,
        "source_commits": SOURCE_COMMITS,
        "components": {
            "python_core": {
                "distribution": "hive-hub",
                "import": "hive_hub",
                "version": VERSION,
            },
            "python_adapters": {
                "import": "adapters",
                "optional": True,
                "version": VERSION,
            },
            "skill": {
                "name": "hive-hub",
                "path": "skills/hive-hub",
                "version": VERSION,
            },
            "static": {
                "api_contract_version": "1.0.0",
                "package": "hive-hub-static-web",
                "version": VERSION,
            },
        },
        "public_api_paths": [
            "/.well-known/hive-hub.json",
            "/api/hive-hub/v1/",
            "/api/hive-hub/v1/core-schemas/",
            "/api/hive-hub/v1/release.json",
            "/hub/",
            "/hub/join/",
            "/llms.txt",
        ],
        "privacy": {
            "classification": "public-only",
            "private_inputs_read": 0,
            "sample": (
                "billwhalenmsft/softwarecoellc-vteam-hive@"
                "f66da3d879b53a439bc87de764d79f68ceec048a"
            ),
        },
        "file_count": len(files),
        "inventory_sha256": inventory_root,
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = canonical(build_manifest())
    if args.check:
        try:
            current = read_regular_bytes(TARGET)
        except FileIntegrityError:
            current = None
        if current != expected:
            print("release/release-manifest.json is out of date")
            return 1
        print("release manifest is current")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() or TARGET.is_symlink():
        read_regular_bytes(TARGET)
    TARGET.write_bytes(expected)
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
