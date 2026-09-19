#!/usr/bin/env python3
"""Verify package bytes and optionally exercise native SDK setup in temporary fixtures."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from scripts.file_integrity import read_regular_bytes  # noqa: E402
from scripts.organization_seeds import (  # noqa: E402
    SEED_SLUGS,
    build_all,
    deterministic_zip,
    relative_path,
    require,
    sha,
)


def verify_package(seed: dict[str, Any]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for entry in seed["files"]:
        path = relative_path(entry["path"])
        require(path not in files, "duplicate package file")
        data = entry["content"].encode("utf-8")
        require(len(data) == entry["bytes"] and sha(data) == entry["sha256"], "file hash mismatch")
        files[path] = data
    require(len(files) == seed["counts"]["packageFiles"], "package count mismatch")
    require("LICENSE" in files and b"MIT License" in files["LICENSE"], "package license missing")
    archive = base64.b64decode(seed["archive"]["base64"], validate=True)
    require(
        len(archive) == seed["archive"]["bytes"] and sha(archive) == seed["archive"]["sha256"],
        "archive hash mismatch",
    )
    require(archive == deterministic_zip(files), "archive differs from the reviewed file inventory")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        require(zipped.namelist() == sorted(files), "archive path inventory mismatch")
        for path in zipped.namelist():
            require(zipped.read(path) == files[path], "archive file bytes mismatch")
    manifest = json.loads(files["seed.json"])
    require(
        manifest["status"] == "seed-not-activated"
        and manifest["authority"] == "inert-starter-data",
        "seed claims activation",
    )
    require(
        {entry["path"] for entry in manifest["inventory"]} == set(files) - {"seed.json"},
        "manifest does not cover every package file",
    )
    for entry in manifest["inventory"]:
        require(
            sha(files[entry["path"]]) == entry["sha256"]
            and len(files[entry["path"]]) == entry["bytes"],
            "manifest file commitment mismatch",
        )
    for task in seed["tasks"]:
        require(
            task["state"] == ("ready" if not task["depends_on"] else "blocked")
            and task["assignee"] is None
            and task["completed_evidence"] == [],
            "seed must not invent completed or assigned work",
        )
    return files


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        text=True,
        env={
            "PATH": os.environ.get("PATH", os.defpath),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
        },
    ).strip()


def qualify_sdk(sdk: Path, parent: Path, dependencies: dict[str, Any]) -> None:
    for root, expected in (
        (sdk, dependencies["sdk"]["commit"]),
        (parent, dependencies["protocol"]["commit"]),
    ):
        require(not root.is_symlink(), "canonical dependency root must not be a symlink")
        require(_git(root, "rev-parse", "HEAD") == expected, "canonical dependency commit mismatch")
        require(
            not _git(root, "status", "--porcelain", "--untracked-files=all"), "dependency is dirty"
        )
        flags = _git(root, "ls-files", "-v").splitlines()
        require(
            all(line.startswith("H ") for line in flags),
            "dependency has hidden index flags",
        )
        for line in _git(root, "ls-tree", "-r", "HEAD").splitlines():
            metadata, relative = line.split("\t", 1)
            mode, kind, object_id = metadata.split()
            require(kind == "blob" and mode in {"100644", "100755"}, "unqualified dependency entry")
            data = read_regular_bytes(root / relative)
            blob = f"blob {len(data)}\0".encode("ascii") + data
            require(
                hashlib.sha1(blob, usedforsecurity=False).hexdigest() == object_id,
                "dependency file differs from its exact commit",
            )
        ignored = _git(root, "ls-files", "--others", "--ignored", "--exclude-standard").splitlines()
        require(
            not any(Path(item).suffix in {".py", ".so", ".pyd"} for item in ignored),
            "dependency contains ignored importable code",
        )
    require(
        sha(read_regular_bytes(sdk / dependencies["sdk"]["entrypoint"]))
        == dependencies["sdk"]["entrypoint_sha256"],
        "SDK entrypoint bytes mismatch",
    )
    require(
        sha(read_regular_bytes(parent / "SPEC.md"))
        == dependencies["protocol"]["specification_sha256"]
        and sha(read_regular_bytes(parent / "rapp.py"))
        == dependencies["protocol"]["reference_sha256"],
        "RAPP/1 parent bytes mismatch",
    )


def exercise_native(seeds: list[dict[str, Any]], sdk: Path, parent: Path) -> list[dict[str, Any]]:
    qualify_sdk(sdk, parent, seeds[0]["dependencies"])
    sys.path.insert(0, str(sdk / "src"))
    from rapp_work import Organization, Workspace, scaffold

    results = []
    with tempfile.TemporaryDirectory(prefix="hive-hub-seed-conformance-") as temporary:
        root = Path(temporary).resolve()
        for seed in seeds:
            files = verify_package(seed)
            setup = json.loads(files["initialize.json"])
            fixture = root / seed["slug"]
            fixture.mkdir()
            (fixture / "workspaces").mkdir()

            def create(request: dict[str, Any], target: Path) -> None:
                inputs = {**request, "owner_label": "seed-conformance", "root": str(target)}
                planned = scaffold(inputs)
                require(planned["status"] == "planned", "native scaffold did not return a plan")
                require(not target.exists(), "planning created a workspace")
                result = planned["result"]
                rejected = scaffold(
                    {
                        **inputs,
                        "apply": True,
                        "plan": result["plan"],
                        "plan_sha256": "0" * 64,
                    }
                )
                require(
                    rejected["status"] == "refused" and not target.exists(),
                    "native setup did not refuse an unapproved digest before effects",
                )
                applied = scaffold(
                    {
                        **inputs,
                        "apply": True,
                        "plan": result["plan"],
                        "plan_sha256": result["plan_sha256"],
                    }
                )
                require(applied["status"] == "applied", "native conformance scaffold failed")

            org_spec = setup["organization"]
            org_path = fixture / relative_path(org_spec["directory"])
            create(org_spec["scaffold"], org_path)
            organization = Organization.load(org_path)
            workspace_count = 0
            for member in setup["workspaces"]:
                workspace_path = fixture / relative_path(member["directory"])
                create(member["scaffold"], workspace_path)
                workspace = Workspace.load(workspace_path)
                prefix = relative_path(member["template"]) + "/"
                for file_path, data in files.items():
                    if file_path.startswith(prefix):
                        relative = relative_path(file_path[len(prefix) :])
                        require(relative.startswith("work/"), "template escaped the work namespace")
                        destination = workspace_path / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with destination.open("xb") as output:
                            output.write(data)
                require(workspace.verify()["status"] == "verified", "native workspace failed")
                plan = organization.plan_register(workspace)
                organization.apply_register(workspace, plan, plan_sha256=plan.sha256)
                workspace_count += 1
            checked = organization.verify()
            require(checked["pointers"] == workspace_count, "native membership count mismatch")
            require(
                all(
                    pointer["world_id"] == seed["organization"]["scaffold"]["world_id"]
                    for pointer in organization.pointers()
                ),
                "native workspace world drift",
            )
            board = json.loads(
                read_regular_bytes(fixture / "workspaces/casework/work/task-board.json")
            )
            require(len(board["tasks"]) == seed["counts"]["tasks"], "case tasks lost during setup")
            results.append(
                {
                    "slug": seed["slug"],
                    "nativeOrganization": "verified",
                    "nativeWorkspaces": workspace_count,
                    "readyTasks": sum(task["state"] == "ready" for task in board["tasks"]),
                    "packageSha256": seed["archive"]["sha256"],
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise-native", action="store_true")
    parser.add_argument("--sdk-path", type=Path, default=ROOT / ".hive-hub/deps/rapp-work")
    parser.add_argument("--rapp1-path", type=Path, default=ROOT / ".hive-hub/deps/rapp-1")
    args = parser.parse_args()
    seeds = build_all(check=True)
    require(tuple(seed["slug"] for seed in seeds) == SEED_SLUGS, "catalog membership drift")
    for seed in seeds:
        verify_package(seed)
    native = exercise_native(seeds, args.sdk_path, args.rapp1_path) if args.exercise_native else []
    print(
        json.dumps(
            {
                "kind": "organization-seed-conformance",
                "seeds": len(seeds),
                "packageFiles": sum(seed["counts"]["packageFiles"] for seed in seeds),
                "nativeFixtures": native,
                "scope": "isolated temporary test fixtures; no user workspace or estate activated",
                "authority": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
