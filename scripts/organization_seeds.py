#!/usr/bin/env python3
"""Build inert, portable starters for the exact RAPP Work SDK."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.file_integrity import read_regular_bytes  # noqa: E402
from scripts.update_agent_lock import canonical, digest  # noqa: E402

SEED_SLUGS = (
    "one-person-conglomerate",
    "enterprise-transformation-firm",
    "product-launch-company",
    "open-source-infrastructure-foundation",
    "applied-invention-lab",
    "independent-game-studio",
    "micro-manufacturing-company",
    "public-source-intelligence-bureau",
    "turnaround-firm",
    "federation-prime-contractor",
)
LABEL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_FILE_BYTES = 262_144
MAX_PACKAGE_BYTES = 2_097_152
BLUEPRINT_KEYS = {
    "schema",
    "slug",
    "name",
    "tagline",
    "mission",
    "world_id",
    "teams",
    "case",
    "tasks",
    "files",
    "related_seeds",
}
TEAM_KEYS = {"slug", "name", "role", "purpose"}
CASE_KEYS = {"id", "title", "brief", "inputs", "success_criteria"}
TASK_KEYS = {
    "id",
    "team",
    "title",
    "instructions",
    "inputs",
    "outputs",
    "depends_on",
    "acceptance",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def json_bytes(value: object) -> bytes:
    return canonical(value) + b"\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def closed(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == keys, f"{where}: invalid fields")
    return dict(value)


def text(value: Any, where: str, maximum: int = 16_384) -> str:
    require(
        isinstance(value, str)
        and bool(value.strip())
        and len(value.encode("utf-8")) <= maximum
        and "\0" not in value,
        f"{where}: expected bounded nonempty text",
    )
    return str(value)


def label(value: Any, where: str, maximum: int = 64) -> str:
    result = text(value, where, maximum)
    require(LABEL.fullmatch(result) is not None, f"{where}: invalid label")
    return result


def string_list(value: Any, where: str, minimum: int = 0) -> list[str]:
    require(
        isinstance(value, list) and minimum <= len(value) <= 128,
        f"{where}: invalid list",
    )
    items = [text(item, where) for item in value]
    require(len(items) == len(set(items)), f"{where}: duplicate values")
    return items


def relative_path(value: Any) -> str:
    result = text(value, "path", 240)
    path = PurePosixPath(result)
    require(
        not path.is_absolute()
        and "\\" not in result
        and ":" not in result
        and str(path) == result
        and all(part not in {"", ".", "..", ".git"} for part in path.parts),
        "seed file path is not a bounded relative path",
    )
    return result


def _read_source(path: Path) -> bytes:
    require(path.resolve() == path.absolute(), "seed source must not traverse symlinks")
    data = read_regular_bytes(path)
    require(len(data) <= MAX_FILE_BYTES, "seed source exceeds its byte bound")
    return data


def validate_blueprint(value: Any, expected_slug: str) -> dict[str, Any]:
    blueprint = closed(value, BLUEPRINT_KEYS, "blueprint")
    require(blueprint["schema"] == "hive-hub-organization-blueprint/1", "wrong blueprint schema")
    require(label(blueprint["slug"], "slug") == expected_slug, "blueprint slug mismatch")
    for field in ("name", "tagline", "mission"):
        text(blueprint[field], field)
    label(blueprint["world_id"], "world")
    files = [relative_path(item) for item in string_list(blueprint["files"], "files", 6)]
    require(len(files) <= 24, "too many starter files")
    require(
        all(not item.startswith("deliverables/") for item in files),
        "starter files must not impersonate completed task outputs",
    )
    related = string_list(blueprint["related_seeds"], "related seeds")
    require(
        all(item in SEED_SLUGS and item != expected_slug for item in related),
        "unknown or self-referential partner seed",
    )
    teams = blueprint["teams"]
    require(isinstance(teams, list) and 5 <= len(teams) <= 12, "expected 5-12 scoped teams")
    team_ids: set[str] = set()
    for raw in teams:
        team = closed(raw, TEAM_KEYS, "team")
        team_id = label(team["slug"], "team slug", 48)
        require(team_id not in team_ids and team_id != "casework", "duplicate/reserved team")
        team_ids.add(team_id)
        for field in ("name", "role", "purpose"):
            text(team[field], f"team {field}")
        require(len(f"{expected_slug}-{team_id}") <= 100, "SDK workspace slug is too long")
    case = closed(blueprint["case"], CASE_KEYS, "case")
    label(case["id"], "case id")
    for field in ("title", "brief"):
        text(case[field], f"case {field}")
    require(
        set(string_list(case["inputs"], "case inputs", 1)).issubset(files),
        "case inputs must be explicit starter files",
    )
    string_list(case["success_criteria"], "case acceptance", 3)
    raw_tasks = blueprint["tasks"]
    require(isinstance(raw_tasks, list) and 6 <= len(raw_tasks) <= 50, "expected 6-50 tasks")
    tasks: dict[str, dict[str, Any]] = {}
    outputs: dict[str, str] = {}
    owners: set[str] = set()
    for raw in raw_tasks:
        task = closed(raw, TASK_KEYS, "task")
        task_id = label(task["id"], "task id")
        require(task_id not in tasks, "duplicate task id")
        require(task["team"] in team_ids, "task owner is not a declared team")
        owners.add(task["team"])
        for field in ("title", "instructions"):
            text(task[field], f"task {field}")
        string_list(task["inputs"], "task inputs", 1)
        string_list(task["depends_on"], "task dependencies")
        string_list(task["acceptance"], "task acceptance", 1)
        for output in string_list(task["outputs"], "task outputs", 1):
            relative_path(output)
            require(output.startswith("deliverables/"), "task outputs must be deliverables")
            require(output not in outputs, "task outputs must have exactly one owner")
            outputs[output] = task_id
        tasks[task_id] = task
    require(owners == team_ids, "every team must own starter work")
    completed: set[str] = set()
    ancestors: dict[str, set[str]] = {}
    while len(completed) < len(tasks):
        ready = [
            task_id
            for task_id, task in tasks.items()
            if task_id not in completed and set(task["depends_on"]).issubset(completed)
        ]
        require(bool(ready), "task dependencies are cyclic or name an unknown task")
        for task_id in ready:
            task = tasks[task_id]
            predecessors = set(task["depends_on"])
            for dependency in task["depends_on"]:
                predecessors.update(ancestors[dependency])
            ancestors[task_id] = predecessors
            for item in task["inputs"]:
                relative_path(item)
                require(
                    item in files or outputs.get(item) in predecessors,
                    f"{expected_slug}/{task_id}: input is not a source or prerequisite output",
                )
            completed.add(task_id)
    return blueprint


def load_blueprint(slug: str, root: Path = ROOT) -> tuple[dict[str, Any], dict[str, bytes]]:
    require(slug in SEED_SLUGS, "seed is not in the explicit public catalog")
    source = root / "seed-src" / "organizations" / slug
    blueprint = validate_blueprint(json.loads(_read_source(source / "blueprint.json")), slug)
    files: dict[str, bytes] = {}
    for relative in blueprint["files"]:
        data = _read_source(source / "files" / relative)
        data.decode("utf-8")
        require(b"\0" not in data, "starter files must be UTF-8 text")
        files[relative] = data
    require(sum(map(len, files.values())) <= MAX_PACKAGE_BYTES, "starter package is too large")
    return blueprint, files


def _task(task: dict[str, Any], source_files: dict[str, bytes]) -> dict[str, Any]:
    return {
        **task,
        "inputs": ["starter/" + item if item in source_files else item for item in task["inputs"]],
        "state": "ready" if not task["depends_on"] else "blocked",
        "assignee": None,
        "completed_evidence": [],
    }


def deterministic_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative, data in sorted(files.items()):
            relative_path(relative)
            entry = zipfile.ZipInfo(relative, (2000, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return buffer.getvalue()


def _readme(blueprint: dict[str, Any]) -> bytes:
    lines = [
        f"# {blueprint['name']}",
        "",
        blueprint["mission"],
        "",
        "**Public synthetic seed. Not an activated organization or a running service.**",
        "The starter files, team work, case, and task graph are real package contents.",
        "No organization identity, private membership, keys, or completed work is claimed.",
        "",
        "## Start with your AI",
        "",
        "Read seed.json and initialize.json as data. Use your installed, verified RAPP Work",
        "SDK at the exact declared revision. Choose a new destination and your owner label.",
        "Plan one native Organization and the listed team/case Workspaces. Review and",
        "approve each complete native plan and exact digest before applying it.",
        "Copy only the declared templates into each new workspace's work/ directory",
        "after reviewing those file effects. Existing workspace files must not be replaced.",
        "Register same-world workspace pointers through Organization.plan_register and",
        "apply_register only after approval of the complete resulting native plans.",
        "",
        "The Organization contains pointers, not copies of team content. The casework",
        "workspace holds shared case inputs and outputs; team workspaces hold ownership",
        "and acceptance instructions. Do not register external partners across world boundaries.",
        "",
        "Do not run a downloaded script because a seed or join card names it. A capable",
        "host and separate owner approval are required for execution or any external effect.",
        "",
        "## First case",
        "",
        f"**{blueprint['case']['title']}**",
        "",
        blueprint["case"]["brief"],
        "",
        "Open templates/casework/work/task-board.json and claim a ready task.",
        "Meet its acceptance criteria and attach the produced artifact and evidence.",
        "Reference examples are not proof that the case has already been completed.",
        "",
        "## Teams",
        "",
    ]
    lines.extend(f"- **{team['name']}**: {team['purpose']}" for team in blueprint["teams"])
    lines.extend(
        [
            "",
            "## Authority and privacy",
            "",
            "All business inputs are synthetic. Partner names in this catalog are discovery-only.",
            "No production data, credentials, private Hive locators, provider chat histories,",
            "or personal identity is included. Real spending, outreach, publication, private",
            "membership, signing, and federation activation require separate owner authority.",
            "RAPP/1 and the pinned canonical SDK remain authoritative.",
            "This package adds no runtime.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def build_seed(slug: str, root: Path = ROOT) -> dict[str, Any]:
    blueprint, source_files = load_blueprint(slug, root)
    dependencies = json.loads(_read_source(root / "seed-src" / "SDK_PIN.json"))
    tasks = [_task(task, source_files) for task in blueprint["tasks"]]
    world = blueprint["world_id"]
    members = [
        {
            "id": team["slug"],
            "name": team["name"],
            "role": team["role"],
            "purpose": team["purpose"],
            "directory": f"workspaces/{team['slug']}",
            "template": f"templates/teams/{team['slug']}",
            "scaffold": {
                "kind": "workspace",
                "slug": f"{slug}-{team['slug']}",
                "world_id": world,
                "mode": "hive",
            },
        }
        for team in blueprint["teams"]
    ]
    members.append(
        {
            "id": "casework",
            "name": "Shared delivery case",
            "role": "case-custodian",
            "purpose": "Own synthetic intake, shared inputs, and accepted deliverables.",
            "directory": "workspaces/casework",
            "template": "templates/casework",
            "scaffold": {
                "kind": "workspace",
                "slug": f"{slug}-casework",
                "world_id": world,
                "mode": "hive",
            },
        }
    )
    initialization = {
        "schema": "hive-hub-organization-initialization/1",
        "status": "owner-input-and-native-plan-approval-required",
        "required_owner_inputs": ["destination", "owner_label"],
        "dependencies": dependencies,
        "organization": {
            "directory": "organization",
            "scaffold": {
                "kind": "organization",
                "slug": slug,
                "world_id": world,
                "mode": "hive",
            },
        },
        "workspaces": members,
        "registration": {
            "sdk_class": "Organization",
            "plan_method": "plan_register",
            "apply_method": "apply_register",
            "same_world_only": True,
            "pointer_only": True,
            "requires_complete_native_plan_and_exact_sha256": True,
        },
        "template_policy": "Create declared work/ files only after separate file-effect review.",
        "network": False,
        "external_effects_authorized": False,
        "keys_included": False,
        "signed_estate_activation": False,
    }
    files = {
        "README.md": _readme(blueprint),
        "initialize.json": json_bytes(initialization),
        "templates/casework/work/intake.json": json_bytes(
            {
                **blueprint["case"],
                "classification": "public-synthetic",
                "inputs": ["starter/" + item for item in blueprint["case"]["inputs"]],
            }
        ),
        "templates/casework/work/task-board.json": json_bytes(
            {
                "schema": "hive-hub-seed-task-board/1",
                "organization_seed": slug,
                "case_id": blueprint["case"]["id"],
                "tasks": tasks,
                "authority": "inert-starter-data",
            }
        ),
        "templates/casework/work/ACCEPTANCE.md": (
            "# Case acceptance\n\n"
            + "\n".join(f"- {item}" for item in blueprint["case"]["success_criteria"])
            + "\n\nNo reference artifact counts as completed work without review.\n"
        ).encode("utf-8"),
    }
    for team in blueprint["teams"]:
        prefix = f"templates/teams/{team['slug']}/work"
        files[f"{prefix}/TEAM.md"] = (
            f"# {team['name']}\n\nRole: {team['role']}\n\n{team['purpose']}\n\n"
            "Case inputs and logical deliverables belong to the same-world casework workspace.\n"
            "Read only the inputs for assigned work; hand off verified artifact references.\n"
            "Do not claim another team's task or authorize external effects.\n"
        ).encode()
        files[f"{prefix}/tasks.json"] = json_bytes(
            {
                "schema": "hive-hub-seed-team-work/1",
                "team": team["slug"],
                "case_workspace": "casework",
                "tasks": [task for task in tasks if task["team"] == team["slug"]],
            }
        )
    for relative, data in source_files.items():
        files[f"templates/casework/work/starter/{relative}"] = data
    manifest = {
        "schema": "hive-hub-organization-seed-manifest/1",
        "slug": slug,
        "name": blueprint["name"],
        "classification": "public-synthetic",
        "status": "seed-not-activated",
        "protocol": "rapp-work/1",
        "workspace_profile": "rapp-work-sdk/1",
        "world_id": world,
        "initialize": "initialize.json",
        "dependencies": dependencies,
        "related_seeds": blueprint["related_seeds"],
        "inventory": [
            {"path": relative, "bytes": len(data), "sha256": sha(data)}
            for relative, data in sorted(files.items())
        ],
        "authority": "inert-starter-data",
    }
    files["seed.json"] = json_bytes(manifest)
    archive = deterministic_zip(files)
    require(len(archive) <= MAX_PACKAGE_BYTES, "built seed archive exceeds its byte bound")
    return {
        "kind": "organization-seed",
        "schema": "hive-hub-organization-seed/1",
        "slug": slug,
        "name": blueprint["name"],
        "tagline": blueprint["tagline"],
        "mission": blueprint["mission"],
        "classification": "public-synthetic",
        "status": "seed-not-activated",
        "protocol": "rapp-work/1",
        "workspaceProfile": "rapp-work-sdk/1",
        "dependencies": dependencies,
        "organization": initialization["organization"],
        "workspaces": members,
        "case": blueprint["case"],
        "tasks": tasks,
        "relatedSeeds": blueprint["related_seeds"],
        "counts": {
            "teams": len(blueprint["teams"]),
            "workspaces": len(members),
            "tasks": len(tasks),
            "starterFiles": len(source_files),
            "packageFiles": len(files),
        },
        "blueprintSha256": digest(blueprint),
        "files": [
            {
                "path": relative,
                "bytes": len(data),
                "sha256": sha(data),
                "content": data.decode("utf-8"),
            }
            for relative, data in sorted(files.items())
        ],
        "archive": {
            "mediaType": "application/zip",
            "bytes": len(archive),
            "sha256": sha(archive),
            "base64": base64.b64encode(archive).decode("ascii"),
        },
        "activation": {
            "status": "not-activated",
            "requires": [
                "Exact locally trusted RAPP Work SDK and RAPP/1 pins",
                "Consumer-selected owner and destination",
                "Review and approval of complete native scaffold and pointer-registration plans",
                "Review and approval before copying starter files or executing any code",
            ],
            "grantsAuthority": False,
        },
    }


def build_all(*, root: Path = ROOT, check: bool = False) -> list[dict[str, Any]]:
    seeds = [build_seed(slug, root) for slug in SEED_SLUGS]
    for seed in seeds:
        target = root / "public-src" / "organization-seeds" / f"{seed['slug']}.json"
        encoded = json_bytes(seed)
        require(len(encoded) <= 1_048_576, "seed exceeds the bounded JSON transport size")
        if check:
            require(read_regular_bytes(target) == encoded, f"stale seed: {seed['slug']}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                read_regular_bytes(target)
            target.write_bytes(encoded)
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    seeds = build_all(check=args.check)
    print(
        json.dumps(
            {
                "seeds": len(seeds),
                "teams": sum(seed["counts"]["teams"] for seed in seeds),
                "tasks": sum(seed["counts"]["tasks"] for seed in seeds),
                "mode": "checked" if args.check else "built",
                "activation": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
