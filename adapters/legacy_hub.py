"""Inert local inspector for historical RAPP_Hub@00ac2f73 data."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    AdapterRefusal,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    contract_document,
    require,
    sha256_bytes,
)

LEGACY_COMPONENT = "RAPP_Hub@00ac2f73"
LEGACY_HUB_PROTOCOL = "legacy-rapp-hub/00ac2f73"
MAX_JSON_BYTES = 1_048_576
MAX_TOTAL_BYTES = 8_388_608
MAX_JSON_FILES = 512
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_DIMENSIONS = 256

_LEGACY_HUB_CONTRACT = {
    "schema": LEGACY_HUB_PROTOCOL,
    "component": LEGACY_COMPONENT,
    "accepted_input": "already-local-json-only",
    "manifest_paths": ["manifest.json", "worlds/manifest.json"],
    "follows_declared_world_paths": True,
    "downloads": False,
    "installs": False,
    "imports": False,
    "executes": False,
}
LEGACY_HUB_FINGERPRINT, LEGACY_HUB_LEARNING = contract_document(
    LEGACY_HUB_PROTOCOL,
    _LEGACY_HUB_CONTRACT,
    source=(
        "https://github.com/kody-w/RAPP_Hub/tree/"
        "00ac2f73cade3f64c39359e9a90fca636bc387aa"
    ),
)
LEGACY_HUB_DECLARATION = AdapterDeclaration(
    adapter_id="legacy-rapp-hub-inspector",
    fingerprint=LEGACY_HUB_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "filesystem-read",
            RequirementLevel.REQUIRED,
            "Historical JSON must already exist in a caller-readable local tree.",
        ),
        CapabilityRequirement(
            "network-download",
            RequirementLevel.FORBIDDEN,
            "The inspector never retrieves schemas, URLs, code, or assets.",
        ),
        CapabilityRequirement(
            "code-import",
            RequirementLevel.FORBIDDEN,
            "Historical Python and JavaScript remain unimported inert files.",
        ),
        CapabilityRequirement(
            "code-execution",
            RequirementLevel.FORBIDDEN,
            "Manifest instructions and world content are data only.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "The inspector performs local bounded reads only.",
        ),
    ),
    private_access_modes=(PrivateAccessMode.LOCAL_INERT,),
    learning_bundle=LEGACY_HUB_LEARNING,
    conformance=ConformanceContract(
        profile="legacy-rapp-hub-conformance/1.0",
        fixtures=("adapters/fixtures/legacy_hub",),
        assertions=(
            "historical-manifests-parse",
            "declared-world-json-parse",
            "malicious-instructions-inert",
            "no-download",
            "no-install",
            "no-import",
            "no-execution",
            "path-escape-refused",
        ),
    ),
    authority_model="Historical Hub bytes are observations only and grant no current authority.",
)


@dataclass(frozen=True)
class LegacyJsonRecord:
    path: str
    sha256: str
    byte_count: int
    json_type: str
    top_level_keys: tuple[str, ...]


@dataclass(frozen=True)
class LegacyDimension:
    universe_id: str
    dimension_id: str
    seed: object
    manifest_path: str
    world_json_files: tuple[str, ...]


@dataclass(frozen=True)
class LegacyHubReport:
    component: str
    outcome: AccessOutcome
    root: str
    records: tuple[LegacyJsonRecord, ...]
    dimensions: tuple[LegacyDimension, ...]
    downloads: int = 0
    installs: int = 0
    imports: int = 0
    executions: int = 0
    authority: bool = False


@dataclass
class _Budget:
    bytes_read: int = 0
    files_read: int = 0


def _json_shape(value: object) -> tuple[str, tuple[str, ...]]:
    if type(value) is dict:
        return "object", tuple(sorted(str(key) for key in value))
    if type(value) is list:
        return "array", ()
    if value is None:
        return "null", ()
    if type(value) is bool:
        return "boolean", ()
    if type(value) in {int, float}:
        return "number", ()
    return "string", ()


def _validate_json_bounds(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        require(
            depth <= MAX_JSON_DEPTH and nodes <= MAX_JSON_NODES,
            "legacy-json-limit",
            "Historical JSON exceeds the bounded inspection profile.",
        )
        if type(item) is dict:
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)


def _safe_path(root: Path, relative: str) -> Path:
    require(
        type(relative) is str
        and bool(relative)
        and "\0" not in relative
        and not PurePosixPath(relative).is_absolute()
        and ".." not in PurePosixPath(relative).parts,
        "legacy-path-escape",
        "Historical manifest paths must remain relative to the fixture root.",
    )
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        require(
            not current.is_symlink(),
            "legacy-path-symlink",
            "Historical inspection refuses symlinked inputs.",
        )
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise AdapterRefusal(
            "legacy-path-escape",
            "Historical manifest path escaped the fixture root.",
        ) from error
    return candidate


def _read_json(
    root: Path,
    relative: str,
    budget: _Budget,
) -> tuple[object, LegacyJsonRecord]:
    path = _safe_path(root, relative)
    require(
        path.is_file(),
        "legacy-json-missing",
        "A declared historical JSON file is unavailable.",
    )
    try:
        size = path.stat().st_size
    except OSError as error:
        raise AdapterRefusal(
            "legacy-json-unavailable",
            "Historical JSON metadata is unavailable.",
        ) from error
    require(
        0 <= size <= MAX_JSON_BYTES,
        "legacy-json-limit",
        "Historical JSON file exceeds the bounded inspection profile.",
    )
    budget.bytes_read += size
    budget.files_read += 1
    require(
        budget.bytes_read <= MAX_TOTAL_BYTES and budget.files_read <= MAX_JSON_FILES,
        "legacy-inspection-limit",
        "Historical inspection exceeds the total bounded profile.",
    )
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise AdapterRefusal(
            "legacy-json-invalid",
            "Historical JSON could not be parsed.",
        ) from error
    _validate_json_bounds(value)
    json_type, keys = _json_shape(value)
    return (
        value,
        LegacyJsonRecord(
            path=relative,
            sha256=sha256_bytes(raw),
            byte_count=len(raw),
            json_type=json_type,
            top_level_keys=keys,
        ),
    )


def _json_files_under(root: Path, relative: str) -> tuple[str, ...]:
    directory = _safe_path(root, relative)
    if not directory.exists():
        return ()
    require(
        directory.is_dir(),
        "legacy-world-path",
        "A declared historical world directory is not a directory.",
    )
    found = []
    for current, directories, files in os.walk(directory, followlinks=False):
        current_path = Path(current)
        for name in directories:
            require(
                not (current_path / name).is_symlink(),
                "legacy-path-symlink",
                "Historical inspection refuses symlinked world directories.",
            )
        directories[:] = sorted(directories)
        for name in sorted(files):
            path = current_path / name
            require(
                not path.is_symlink(),
                "legacy-path-symlink",
                "Historical inspection refuses symlinked world files.",
            )
            if path.suffix.lower() != ".json":
                continue
            found.append(path.relative_to(root).as_posix())
            require(
                len(found) <= MAX_JSON_FILES,
                "legacy-inspection-limit",
                "Historical world contains too many JSON files.",
            )
    return tuple(found)


class LegacyRappHubInspector:
    declaration = LEGACY_HUB_DECLARATION

    def inspect(self, root: str | os.PathLike[str]) -> LegacyHubReport:
        supplied = Path(root).expanduser()
        require(
            not supplied.is_symlink(),
            "legacy-root-invalid",
            "Historical Hub inspection refuses a symlinked root.",
        )
        try:
            base = supplied.resolve(strict=True)
        except OSError as error:
            raise AdapterRefusal(
                "legacy-root-invalid",
                "Historical Hub inspection requires an existing local directory.",
            ) from error
        require(
            base.is_dir() and not base.is_symlink(),
            "legacy-root-invalid",
            "Historical Hub inspection requires a local non-symlink directory.",
        )
        budget = _Budget()
        records: dict[str, LegacyJsonRecord] = {}

        root_manifest = base / "manifest.json"
        if root_manifest.is_file() and not root_manifest.is_symlink():
            _, record = _read_json(base, "manifest.json", budget)
            records[record.path] = record

        worlds_value, record = _read_json(base, "worlds/manifest.json", budget)
        records[record.path] = record
        require(
            type(worlds_value) is dict and type(worlds_value.get("universes")) is list,
            "legacy-worlds-manifest",
            "Historical worlds manifest has an unknown shape.",
        )
        worlds = cast(dict[str, Any], worlds_value)

        dimensions: list[LegacyDimension] = []
        for universe_value in worlds["universes"]:
            require(
                type(universe_value) is dict
                and type(universe_value.get("id")) is str
                and type(universe_value.get("dimensions")) is list,
                "legacy-worlds-manifest",
                "Historical universe entry has an unknown shape.",
            )
            universe = cast(dict[str, Any], universe_value)
            universe_id = universe["id"]
            for entry_value in universe["dimensions"]:
                require(
                    len(dimensions) < MAX_DIMENSIONS
                    and type(entry_value) is dict
                    and type(entry_value.get("id")) is str
                    and type(entry_value.get("path")) is str,
                    "legacy-worlds-manifest",
                    "Historical dimension entry has an unknown or unbounded shape.",
                )
                entry = cast(dict[str, Any], entry_value)
                dimension_root = f"worlds/{entry['path']}"
                manifest_relative = f"{dimension_root}/manifest.json"
                manifest_value, manifest_record = _read_json(
                    base,
                    manifest_relative,
                    budget,
                )
                records[manifest_record.path] = manifest_record
                require(
                    type(manifest_value) is dict
                    and type(manifest_value.get("dimension")) is dict
                    and type(manifest_value.get("paths", {})) is dict,
                    "legacy-dimension-manifest",
                    "Historical dimension manifest has an unknown shape.",
                )
                manifest = cast(dict[str, Any], manifest_value)
                declared_files = []
                for declared in manifest.get("paths", {}).values():
                    require(
                        type(declared) is str,
                        "legacy-dimension-manifest",
                        "Historical dimension paths must be strings.",
                    )
                    relative = f"{dimension_root}/{declared}"
                    candidate = _safe_path(base, relative)
                    if candidate.is_file() and candidate.suffix.lower() == ".json":
                        declared_files.append(relative)
                    elif candidate.is_dir():
                        declared_files.extend(_json_files_under(base, relative))
                world_files = tuple(sorted(set(declared_files)))
                for world_file in world_files:
                    _, world_record = _read_json(base, world_file, budget)
                    records[world_record.path] = world_record
                dimension = cast(dict[str, Any], manifest["dimension"])
                dimensions.append(
                    LegacyDimension(
                        universe_id=universe_id,
                        dimension_id=str(dimension.get("id", entry["id"])),
                        seed=dimension.get("seed"),
                        manifest_path=manifest_relative,
                        world_json_files=world_files,
                    )
                )

        return LegacyHubReport(
            component=LEGACY_COMPONENT,
            outcome=AccessOutcome.REACHABLE,
            root=str(base),
            records=tuple(records[key] for key in sorted(records)),
            dimensions=tuple(
                sorted(
                    dimensions,
                    key=lambda item: (item.universe_id, item.dimension_id),
                )
            ),
        )
