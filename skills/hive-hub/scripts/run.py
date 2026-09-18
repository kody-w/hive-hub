#!/usr/bin/env python3
"""Locked, protocol-neutral Hive resolver and plan-first join runner."""

from __future__ import annotations

import sys as _bootstrap_sys


def _sanitize_bootstrap_path() -> None:
    """Remove project and package paths before importing anything from disk."""
    stdlib = getattr(_bootstrap_sys, "_stdlib_dir", "")
    if not isinstance(stdlib, str) or not stdlib:
        if not _bootstrap_sys.flags.isolated:
            raise RuntimeError("run this skill with Python isolated mode (-I)")
        return
    normalized_stdlib = stdlib.replace("\\", "/").rstrip("/")
    stdlib_parent = normalized_stdlib.rsplit("/", 1)[0]
    folded_stdlib = normalized_stdlib.casefold()
    folded_parent = stdlib_parent.casefold()
    safe: list[str] = []
    for entry in _bootstrap_sys.path:
        if not isinstance(entry, str) or not entry:
            continue
        normalized = entry.replace("\\", "/").rstrip("/")
        folded = normalized.casefold()
        if any(part in {".", ".."} for part in normalized.split("/")):
            continue
        if "/site-packages" in folded or "/dist-packages" in folded:
            continue
        in_stdlib = folded == folded_stdlib or folded.startswith(
            folded_stdlib + "/"
        )
        in_dlls = folded == folded_parent + "/dlls" or folded.startswith(
            folded_parent + "/dlls/"
        )
        stdlib_zip = (
            folded.startswith(folded_parent + "/python")
            and folded.endswith(".zip")
            and "/" not in folded[len(folded_parent) + 1 :]
        )
        if in_stdlib or in_dlls or stdlib_zip:
            safe.append(entry)
    if not safe:
        raise RuntimeError("Python standard-library path could not be isolated")
    _bootstrap_sys.path[:] = safe


_sanitize_bootstrap_path()
del _sanitize_bootstrap_path

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SKILL_ROOT = Path(__file__).resolve().parents[1]
LOCK_SCHEMA = "hive-hub-agent-lock/1"
RESULT_SCHEMA = "hive-hub-result/1"
PLAN_SCHEMA = "hive-hub-plan/1"
DECLARATION_SCHEMA = "hive-hub-declaration/1"
DIALBOOK_SCHEMA = "hive-hub-dialbook/1"
CARD_SCHEMAS = frozenset(
    {
        "hive-hub-join-card/1",
        "hive-hub-qr-join-card/1",
        "hive-hub-ai-join-card/1",
    }
)
CORE_AI_CARD_KIND = "ai-join-card"
CORE_AI_CARD_SCHEMA_VERSION = 1
CORE_ADDRESS_RE = re.compile(r"^urn:hivehub:sha256:([0-9a-f]{64})$")
OPERATIONS = ("verify", "decode", "dial", "join")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIAL_ID_RE = re.compile(r"^dial:sha256:([0-9a-f]{64})$")
RAPPID_RE = re.compile(
    r"^rappid:@[a-z0-9]+(?:-[a-z0-9]+)*/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*:[0-9a-f]{64}$"
)
CHANT_WORD_RE = re.compile(r"^[a-z]{1,32}$")
GITHUB_OWNER_RE = re.compile(
    r"^(?=.{1,39}$)(?!-)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$"
)
GITHUB_REPOSITORY_RE = re.compile(
    r"^(?=.{1,100}$)(?!\.{1,2}$)[A-Za-z0-9_.-]+$"
)
HEX_REF_RE = re.compile(r"^[0-9A-Fa-f]{7,64}$")
PROTOCOL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}/[0-9]+$")
ADAPTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}/[0-9]+$")
MEDIA_TYPE_RE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/"
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$"
)
SECRET_VALUE_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"bearer[ \t]+[A-Za-z0-9._~+/=-]{12,}|"
    r"(?:password|passwd|token|secret|api[_-]?key)=[^&\s]{4,})",
    re.IGNORECASE,
)
SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|passphrase|secret|token|credential|private[-_]?key|"
    r"api[-_]?key|cookie|authorization|unlock[_-]?fragment)",
    re.IGNORECASE,
)
ACTIVE_SUFFIXES = frozenset(
    {
        ".bat",
        ".cmd",
        ".com",
        ".dll",
        ".dylib",
        ".egg",
        ".exe",
        ".fish",
        ".jar",
        ".node",
        ".php",
        ".pl",
        ".ps1",
        ".pth",
        ".py",
        ".pyc",
        ".pyd",
        ".pyo",
        ".pyw",
        ".rb",
        ".sh",
        ".so",
        ".wasm",
        ".whl",
        ".zip",
        ".zsh",
    }
)
VERIFIED_JOIN_CONTRACT_START = "<!-- microsol-any-ai-setup:start -->"
VERIFIED_JOIN_CONTRACT_END = "<!-- microsol-any-ai-setup:end -->"
VERIFIED_JOIN_COMMAND = ["python3", "-B", "microsol.py", "setup"]
VERIFIED_JOIN_REQUIRED_FILES = frozenset(
    {
        ".github/skills/microsol/SKILL.md",
        "HOME.md",
        "RELEASE-FILES.txt",
        "SKILL.md",
        "join-contract.json",
        "microsol.py",
        "release-lock.json",
    }
)
DECLARATION_PATHS = (
    ".well-known/hive.json",
    "hive.json",
    "HIVE.json",
)


class HubError(RuntimeError):
    code = "hive-hub-refused"
    kind = "verification"
    status = "blocked"
    public_message = "The Hive request could not be completed safely."
    next_action = "Preserve the request and retry after resolving this check."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        learning: dict[str, Any] | None = None,
    ):
        super().__init__(message or self.public_message)
        self.details = details
        self.learning = learning

    def result(self, operation: str) -> dict[str, Any]:
        blocker: dict[str, Any] = {
            "kind": self.kind,
            "code": self.code,
            "message": self.public_message,
            "next_action": self.next_action,
        }
        if self.details:
            blocker["details"] = self.details
        value: dict[str, Any] = {
            "schema": RESULT_SCHEMA,
            "operation": operation,
            "status": self.status,
            "ready": False,
            "blocker": blocker,
        }
        if self.learning is not None:
            value["learning_bundle"] = self.learning
        return value


class InputError(HubError):
    code = "input-invalid"
    kind = "input"
    public_message = "The supplied Hive locator or card is not valid."
    next_action = "Use one accepted canonical locator or a closed join-card JSON object."


class PackageError(HubError):
    code = "skill-lock-invalid"
    kind = "local-integrity"
    public_message = "The local Hive Hub skill does not match its lock."
    next_action = "Replace the whole skill folder with one verified copy."


class StorageError(HubError):
    code = "device-storage-refused"
    kind = "local-storage"
    public_message = "The device-local Hive Hub storage cannot be used safely."
    next_action = "Preserve existing files and select a private, unmanaged-free device root."


class UnreachableError(HubError):
    code = "target-unreachable"
    kind = "access"
    public_message = "The Hive target is unreachable with this device's existing access."
    next_action = "Check the address and existing access, then retry the same request."


class UnknownContractError(HubError):
    code = "contract-unknown"
    kind = "protocol"
    public_message = "The Hive contract is valid but its declared adapter is not known locally."
    next_action = "Approve and install a separately reviewed adapter that conforms to the returned learning bundle."


class ContractError(HubError):
    code = "contract-invalid"
    kind = "protocol"
    public_message = "The Hive declaration or verified join contract is not recognized."
    next_action = "Ask the Hive publisher for a complete pinned declaration and conformance bundle."


class FactorError(HubError):
    code = "second-factor-required"
    kind = "access"
    public_message = "Repository access succeeded, but this Hive also requires its QR factor."
    next_action = "Scan the original card locally and pass it through --card-stdin."


class PlanError(HubError):
    code = "plan-approval-invalid"
    kind = "approval"
    public_message = "The supplied approval does not match the current complete plan."
    next_action = "Review the newly returned plan and approve its exact lowercase digest."


class ExecutionError(HubError):
    code = "adapter-execution-refused"
    kind = "local-execution"
    public_message = "The verified adapter could not complete without crossing its safety contract."
    next_action = "Preserve local state and resolve the verified local blocker before retrying."


class ChantCollisionError(HubError):
    code = "chant-collision"
    kind = "locator"
    public_message = "The seven-word chant matches more than one Dial Record."
    next_action = "Choose one complete Dial Record ID; the skill will not guess."


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UnreachableError()


class LockedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError()


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError() from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value!r}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _bounded_json_shape(value: Any, *, maximum_depth: int, maximum_nodes: int) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > maximum_nodes or depth > maximum_depth:
            raise ValueError("JSON shape exceeds the bounded profile")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise ValueError("JSON object key is not text")
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            for child in current:
                stack.append((child, depth + 1))
        elif current is not None and type(current) not in {
            str,
            int,
            float,
            bool,
        }:
            raise ValueError("JSON contains an unsupported value")


def parse_json(
    raw: bytes,
    *,
    label: str,
    maximum: int,
    maximum_depth: int = 32,
    maximum_nodes: int = 20_000,
) -> Any:
    if not raw or len(raw) > maximum:
        raise ValueError(f"{label} is empty or oversized")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    _bounded_json_shape(
        value,
        maximum_depth=maximum_depth,
        maximum_nodes=maximum_nodes,
    )
    return value


def parse_json_object(
    raw: bytes,
    *,
    label: str,
    maximum: int,
    maximum_depth: int = 32,
    maximum_nodes: int = 20_000,
) -> dict[str, Any]:
    value = parse_json(
        raw,
        label=label,
        maximum=maximum,
        maximum_depth=maximum_depth,
        maximum_nodes=maximum_nodes,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one object")
    return value


def _text(
    value: Any,
    *,
    minimum: int = 1,
    maximum: int,
    ascii_only: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ContractError()
    encoded = value.encode("utf-8")
    if (
        not minimum <= len(encoded) <= maximum
        or "\x00" in value
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
        or ascii_only
        and not value.isascii()
    ):
        raise ContractError()
    return value


def _safe_relative(value: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise ContractError()
    pure = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ContractError()
    return Path(*pure.parts)


def _read_regular(path: Path, maximum: int, *, storage: bool = False) -> bytes:
    error: type[HubError] = StorageError if storage else ContractError
    try:
        information = path.lstat()
        if (
            not stat.S_ISREG(information.st_mode)
            or information.st_nlink != 1
            or information.st_size < 0
            or information.st_size > maximum
        ):
            raise error()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            current = os.fstat(descriptor)
            if (
                current.st_dev != information.st_dev
                or current.st_ino != information.st_ino
                or current.st_size != information.st_size
            ):
                raise error()
            chunks: list[bytes] = []
            remaining = information.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise error()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise error()
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except HubError:
        raise
    except OSError:
        raise error() from None


def _tree_files(root: Path) -> dict[str, os.stat_result]:
    files: dict[str, os.stat_result] = {}

    def visit(directory: Path, prefix: str) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError:
            raise PackageError() from None
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                information = entry.stat(follow_symlinks=False)
            except OSError:
                raise PackageError() from None
            if stat.S_ISLNK(information.st_mode):
                raise PackageError()
            if stat.S_ISDIR(information.st_mode):
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(information.st_mode):
                if information.st_nlink != 1:
                    raise PackageError()
                files[relative] = information
            else:
                raise PackageError()

    visit(root, "")
    return files


def _validate_lock_shape(lock: dict[str, Any]) -> None:
    if set(lock) != {
        "schema",
        "name",
        "version",
        "runner",
        "limits",
        "adapters",
        "verified_join",
        "files",
    }:
        raise PackageError()
    if (
        lock.get("schema") != LOCK_SCHEMA
        or lock.get("name") != "hive-hub"
        or lock.get("version") != "0.1.0"
        or lock.get("runner")
        != {
            "python": ">=3.11",
            "isolated": True,
            "stdlib_only": True,
        }
    ):
        raise PackageError()
    limits = lock.get("limits")
    expected_limits = {
        "card_bytes",
        "dialbook_bytes",
        "dialbook_records",
        "json_bytes",
        "json_depth",
        "json_nodes",
        "git_output_bytes",
        "learning_items",
        "learning_item_bytes",
        "process_seconds",
    }
    if (
        not isinstance(limits, dict)
        or set(limits) != expected_limits
        or any(type(value) is not int or value <= 0 for value in limits.values())
        or limits["card_bytes"] > 65_536
        or limits["dialbook_bytes"] > 4 * 1024 * 1024
        or limits["dialbook_records"] > 4096
        or limits["json_bytes"] > 1024 * 1024
        or limits["json_depth"] > 64
        or limits["json_nodes"] > 100_000
        or limits["git_output_bytes"] > 4 * 1024 * 1024
        or limits["learning_items"] > 128
        or limits["learning_item_bytes"] > 64 * 1024 * 1024
        or limits["process_seconds"] > 900
    ):
        raise PackageError()
    adapters = lock.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        raise PackageError()
    seen: set[str] = set()
    for adapter in adapters:
        if (
            not isinstance(adapter, dict)
            or set(adapter) != {
                "id",
                "fingerprint",
                "contract",
                "implementation",
            }
            or ADAPTER_ID_RE.fullmatch(str(adapter.get("id"))) is None
            or SHA256_RE.fullmatch(str(adapter.get("fingerprint"))) is None
            or adapter["id"] in seen
            or not isinstance(adapter.get("contract"), dict)
            or adapter.get("implementation")
                not in {"local-subscription", "verified-current-main"}
            or digest(adapter["contract"]) != adapter["fingerprint"]
        ):
            raise PackageError()
        seen.add(adapter["id"])
    verified_join = lock.get("verified_join")
    if (
        not isinstance(verified_join, dict)
        or set(verified_join)
        != {
            "contract_sha256",
            "contract",
            "required_files",
        }
        or SHA256_RE.fullmatch(str(verified_join.get("contract_sha256"))) is None
        or not isinstance(verified_join.get("contract"), dict)
        or digest(verified_join["contract"]) != verified_join["contract_sha256"]
        or verified_join["contract"].get("schema") != "microsol-any-ai-setup/2"
        or verified_join["contract"].get("command") != VERIFIED_JOIN_COMMAND
        or not isinstance(verified_join.get("required_files"), list)
        or set(verified_join["required_files"]) != VERIFIED_JOIN_REQUIRED_FILES
    ):
        raise PackageError()


def load_lock() -> dict[str, Any]:
    try:
        raw = _read_regular(SKILL_ROOT / "agent.lock", 1024 * 1024)
        lock = parse_json_object(
            raw,
            label="agent.lock",
            maximum=1024 * 1024,
        )
        _validate_lock_shape(lock)
    except (ValueError, HubError):
        raise PackageError() from None
    records = lock.get("files")
    if not isinstance(records, list) or not records:
        raise PackageError()
    expected: dict[str, dict[str, Any]] = {}
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "bytes", "sha256"}
            or type(record.get("bytes")) is not int
            or not 0 <= record["bytes"] <= 8 * 1024 * 1024
            or SHA256_RE.fullmatch(str(record.get("sha256"))) is None
        ):
            raise PackageError()
        try:
            relative = _safe_relative(str(record["path"])).as_posix()
        except HubError:
            raise PackageError() from None
        if relative == "agent.lock" or relative in expected:
            raise PackageError()
        expected[relative] = record
    actual = _tree_files(SKILL_ROOT)
    actual.pop("agent.lock", None)
    if set(actual) != set(expected):
        raise PackageError()
    for relative, record in expected.items():
        data = _read_regular(SKILL_ROOT / Path(relative), record["bytes"])
        if (
            len(data) != record["bytes"]
            or hashlib.sha256(data).hexdigest() != record["sha256"]
        ):
            raise PackageError()
    return lock


def _canonical_github_url(owner: str, repository: str, branch: str) -> str:
    base = f"https://github.com/{owner}/{repository}"
    return base if branch == "main" else f"{base}/tree/{quote(branch, safe='/')}"


def _validate_branch(branch: str) -> None:
    if (
        not isinstance(branch, str)
        or not branch
        or len(branch.encode("utf-8")) > 255
        or not branch.isascii()
        or branch.startswith(("-", "refs/", "heads/", "tags/", "remotes/"))
        or branch.endswith(("/", "."))
        or branch in {"@", "HEAD"}
        or HEX_REF_RE.fullmatch(branch) is not None
        or ".." in branch
        or "@{" in branch
        or "//" in branch
    ):
        raise InputError()
    forbidden = set(" ~^:?*[\\")
    if any(
        character in forbidden
        or ord(character) < 32
        or ord(character) == 127
        for character in branch
    ):
        raise InputError()
    for component in branch.split("/"):
        if not component or component.startswith(".") or component.endswith(".lock"):
            raise InputError()


def parse_github_address(raw: str) -> dict[str, str]:
    if (
        not isinstance(raw, str)
        or not raw
        or raw != raw.strip()
        or len(raw.encode("utf-8")) > 2048
        or any(ord(character) < 32 or ord(character) == 127 for character in raw)
    ):
        raise InputError()
    owner: str
    repository: str
    branch: str
    if "://" in raw:
        if "%" in raw or "\\" in raw:
            raise InputError()
        parsed = urlsplit(raw)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or parsed.path.endswith("/")
            or "//" in parsed.path
        ):
            raise InputError()
        parts = parsed.path[1:].split("/")
        if len(parts) == 2:
            owner, repository = parts
            branch = "main"
        elif len(parts) >= 4 and parts[2] == "tree":
            owner, repository = parts[:2]
            branch = "/".join(parts[3:])
        else:
            raise InputError()
    else:
        if raw.count(" at ") > 1:
            raise InputError()
        repository_part, separator, supplied_branch = raw.partition(" at ")
        if repository_part.count("/") != 1:
            raise InputError()
        owner, repository = repository_part.split("/", 1)
        branch = supplied_branch if separator else "main"
    if (
        GITHUB_OWNER_RE.fullmatch(owner) is None
        or GITHUB_REPOSITORY_RE.fullmatch(repository) is None
        or repository.casefold().endswith(".git")
    ):
        raise InputError()
    _validate_branch(branch)
    owner = owner.casefold()
    repository = repository.casefold()
    canonical_repository = f"{owner}/{repository}"
    return {
        "kind": "github",
        "repository": canonical_repository,
        "owner": owner,
        "name": repository,
        "branch": branch,
        "remote": f"https://github.com/{canonical_repository}.git",
        "canonical": _canonical_github_url(owner, repository, branch),
    }


def normalize_chant(raw: str) -> str:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 512:
        raise InputError()
    words = raw.strip().lower().replace("-", " ").split()
    if len(words) != 7 or any(CHANT_WORD_RE.fullmatch(word) is None for word in words):
        raise InputError()
    return "-".join(words)


def _looks_like_local_path(raw: str) -> bool:
    return (
        raw.startswith(("/", "./", "../", "~/", ".\\", "..\\"))
        or re.match(r"^[A-Za-z]:[\\/]", raw) is not None
        or raw.startswith("\\\\")
        or Path(os.path.expanduser(raw)).exists()
    )


def _absolute_local_path(raw: str, cwd: Path) -> Path:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise InputError()
    expanded = os.path.expanduser(raw)
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", expanded):
        raise InputError()
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        return Path(os.path.abspath(candidate))
    except (OSError, ValueError):
        raise InputError() from None


def classify_locator(raw: str, cwd: Path) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise InputError()
    if raw.startswith("https://github.com/") or (
        "://" not in raw
        and re.match(r"^[^/\s]+/[^/\s]+(?: at .+)?$", raw) is not None
    ):
        return parse_github_address(raw)
    match = DIAL_ID_RE.fullmatch(raw)
    if match is not None or RAPPID_RE.fullmatch(raw) is not None:
        return {"kind": "dial-id", "value": raw}
    try:
        chant = normalize_chant(raw)
    except InputError:
        chant = None
    if chant is not None:
        return {"kind": "chant", "value": chant}
    if _looks_like_local_path(raw):
        path = _absolute_local_path(raw, cwd)
        return {
            "kind": "local",
            "path": str(path),
            "canonical": path.as_uri() if path.is_absolute() else str(path),
        }
    raise InputError()


def _parse_hive_url(raw: str) -> tuple[str, str | None, str | None]:
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "hive"
        or parsed.netloc != "join"
        or parsed.path not in {"", "/"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InputError()
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if set(query) - {"locator", "workspace"} or any(len(values) != 1 for values in query.values()):
        raise InputError()
    locator = unquote(query.get("locator", [""])[0])
    workspace = unquote(query["workspace"][0]) if "workspace" in query else None
    fragment = unquote(parsed.fragment) if parsed.fragment else None
    if not locator or fragment is not None and not fragment:
        raise InputError()
    return locator, workspace, fragment


def _artifact_reference(
    value: Any,
    *,
    limits: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "role",
        "url",
        "sha256",
        "bytes",
        "media_type",
    }:
        raise ContractError()
    role = _text(value["role"], maximum=64, ascii_only=True)
    if re.fullmatch(r"[a-z][a-z0-9-]{0,63}", role) is None:
        raise ContractError()
    url = _validated_inert_url(value["url"])
    checksum = str(value["sha256"])
    size = value["bytes"]
    media_type = _text(value["media_type"], maximum=128, ascii_only=True)
    if (
        SHA256_RE.fullmatch(checksum) is None
        or type(size) is not int
        or not 0 <= size <= limits["learning_item_bytes"]
        or MEDIA_TYPE_RE.fullmatch(media_type) is None
    ):
        raise ContractError()
    return {
        "role": role,
        "url": url,
        "sha256": checksum,
        "bytes": size,
        "media_type": media_type,
    }


def _validated_inert_url(raw: Any) -> str:
    value = _text(raw, maximum=4096, ascii_only=True)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname.casefold() in {"localhost", "localhost.localdomain"}
        or parsed.hostname.casefold().endswith((".local", ".internal"))
        or re.fullmatch(r"[0-9.]+", parsed.hostname) is not None
        or not parsed.path.startswith("/")
    ):
        raise ContractError()
    if parsed.hostname.casefold() == "raw.githubusercontent.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 4 or COMMIT_RE.fullmatch(parts[2]) is None:
            raise ContractError()
    return value


def validate_learning(
    value: Any,
    *,
    protocol_id: str,
    limits: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "sha256",
        "artifacts",
    }:
        raise ContractError()
    if value.get("schema") != "hive-hub-learning-bundle/1":
        raise ContractError()
    artifacts_raw = value.get("artifacts")
    if (
        not isinstance(artifacts_raw, list)
        or not artifacts_raw
        or len(artifacts_raw) > limits["learning_items"]
    ):
        raise ContractError()
    artifacts = [
        _artifact_reference(item, limits=limits) for item in artifacts_raw
    ]
    roles = {item["role"] for item in artifacts}
    if not {"spec", "conformance"}.issubset(roles):
        raise ContractError()
    if "rapp" in protocol_id.casefold() and not {
        "spec",
        "schema",
        "examples",
        "conformance",
        "skill",
    }.issubset(roles):
        raise ContractError()
    body = {
        "schema": "hive-hub-learning-bundle/1",
        "artifacts": artifacts,
    }
    checksum = str(value.get("sha256"))
    if SHA256_RE.fullmatch(checksum) is None or digest(body) != checksum:
        raise ContractError()
    return {**body, "sha256": checksum}


def validate_declaration(
    value: Any,
    *,
    limits: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in (
        {
            "schema",
            "id",
            "name",
            "access",
            "protocol",
            "adapter",
            "learning",
            "conformance",
            "join",
        },
        {
            "schema",
            "id",
            "name",
            "access",
            "protocol",
            "adapter",
            "learning",
            "conformance",
            "join",
            "extensions",
        },
    ):
        raise ContractError()
    if value.get("schema") != DECLARATION_SCHEMA:
        raise ContractError()
    dial_id = _text(value.get("id"), maximum=96, ascii_only=True)
    if DIAL_ID_RE.fullmatch(dial_id) is None:
        raise ContractError()
    name = _text(value.get("name"), maximum=160)
    access = value.get("access")
    if not isinstance(access, dict) or set(access) not in (
        {"visibility"},
        {"visibility", "mode"},
        {"visibility", "mode", "unlock_sha256"},
    ):
        raise ContractError()
    visibility = access.get("visibility")
    mode = access.get("mode", "acl-only")
    if visibility not in {"public", "private"} or mode not in {
        "acl-only",
        "acl+qr",
    }:
        raise ContractError()
    unlock_sha256 = access.get("unlock_sha256")
    if mode == "acl+qr":
        if SHA256_RE.fullmatch(str(unlock_sha256)) is None:
            raise ContractError()
    elif unlock_sha256 is not None:
        raise ContractError()
    protocol = value.get("protocol")
    if not isinstance(protocol, dict) or set(protocol) != {
        "id",
        "fingerprint",
        "spec_sha256",
    }:
        raise ContractError()
    protocol_id = str(protocol.get("id"))
    fingerprint = str(protocol.get("fingerprint"))
    spec_sha256 = str(protocol.get("spec_sha256"))
    if (
        PROTOCOL_ID_RE.fullmatch(protocol_id) is None
        or SHA256_RE.fullmatch(fingerprint) is None
        or SHA256_RE.fullmatch(spec_sha256) is None
        or fingerprint != spec_sha256
    ):
        raise ContractError()
    adapter = value.get("adapter")
    if not isinstance(adapter, dict) or set(adapter) != {
        "id",
        "fingerprint",
    }:
        raise ContractError()
    adapter_id = str(adapter.get("id"))
    adapter_fingerprint = str(adapter.get("fingerprint"))
    if (
        ADAPTER_ID_RE.fullmatch(adapter_id) is None
        or SHA256_RE.fullmatch(adapter_fingerprint) is None
    ):
        raise ContractError()
    learning = validate_learning(
        value.get("learning"),
        protocol_id=protocol_id,
        limits=limits,
    )
    roles = {
        item["role"]: item["sha256"] for item in learning["artifacts"]
    }
    if roles.get("spec") != spec_sha256:
        raise ContractError()
    conformance = value.get("conformance")
    if not isinstance(conformance, dict) or set(conformance) != {
        "id",
        "artifact_sha256",
    }:
        raise ContractError()
    conformance_id = _text(
        conformance.get("id"), maximum=128, ascii_only=True
    )
    conformance_sha = str(conformance.get("artifact_sha256"))
    if (
        PROTOCOL_ID_RE.fullmatch(conformance_id) is None
        or SHA256_RE.fullmatch(conformance_sha) is None
        or roles.get("conformance") != conformance_sha
    ):
        raise ContractError()
    join = value.get("join")
    if not isinstance(join, dict) or set(join) != {"kind", "next_step"}:
        raise ContractError()
    kind = join.get("kind")
    next_step = _text(join.get("next_step"), maximum=2048)
    if kind not in {"subscription", "verified-current-main"}:
        raise ContractError()
    if SECRET_VALUE_RE.search(next_step):
        raise ContractError()
    normalized: dict[str, Any] = {
        "schema": DECLARATION_SCHEMA,
        "id": dial_id,
        "name": name,
        "access": {
            "visibility": visibility,
            "mode": mode,
            **(
                {"unlock_sha256": str(unlock_sha256)}
                if unlock_sha256 is not None
                else {}
            ),
        },
        "protocol": {
            "id": protocol_id,
            "fingerprint": fingerprint,
            "spec_sha256": spec_sha256,
        },
        "adapter": {
            "id": adapter_id,
            "fingerprint": adapter_fingerprint,
        },
        "learning": learning,
        "conformance": {
            "id": conformance_id,
            "artifact_sha256": conformance_sha,
        },
        "join": {"kind": kind, "next_step": next_step},
    }
    if "extensions" in value:
        extensions = value["extensions"]
        if not isinstance(extensions, dict):
            raise ContractError()
        _bounded_json_shape(
            extensions,
            maximum_depth=limits["json_depth"],
            maximum_nodes=limits["json_nodes"],
        )
        normalized["extensions"] = extensions
    return normalized


def _validate_static_reference(value: Any, limits: dict[str, int]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"url", "sha256", "bytes"}:
        raise InputError()
    url = _validated_inert_url(value["url"])
    checksum = str(value["sha256"])
    size = value["bytes"]
    if (
        not url.endswith(".json")
        or SHA256_RE.fullmatch(checksum) is None
        or type(size) is not int
        or not 1 <= size <= limits["json_bytes"]
    ):
        raise InputError()
    return {"url": url, "sha256": checksum, "bytes": size}


def _parse_core_ai_join_card(card: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "kind",
        "schema_version",
        "card_id",
        "principal",
        "locator",
        "expected_record_id",
        "expected_protocol_fingerprint",
        "adapter_plan",
        "issued_at",
    }
    if (
        set(card) != expected_keys
        or card.get("kind") != CORE_AI_CARD_KIND
        or card.get("schema_version") != CORE_AI_CARD_SCHEMA_VERSION
        or card.get("adapter_plan") is not None
        or card.get("expected_record_id") is not None
        or card.get("expected_protocol_fingerprint") is not None
    ):
        raise InputError()
    principal = card.get("principal")
    if (
        not isinstance(principal, dict)
        or set(principal) != {"kind", "id"}
        or principal.get("kind") not in {"human", "ai"}
    ):
        raise InputError()
    principal_id = _text(principal.get("id"), maximum=512)
    locator = _text(card.get("locator"), maximum=4096)
    issued_at = _text(card.get("issued_at"), maximum=32, ascii_only=True)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", issued_at) is None:
        raise InputError()
    body = {
        "kind": "ai-join-card-body",
        "schema_version": CORE_AI_CARD_SCHEMA_VERSION,
        "principal": {"kind": principal["kind"], "id": principal_id},
        "locator": locator,
        "expected_record_id": None,
        "expected_protocol_fingerprint": None,
        "adapter_plan": None,
        "issued_at": issued_at,
    }
    if card.get("card_id") != "urn:hivehub:sha256:" + digest(body):
        raise InputError()
    card.clear()
    return {
        "locator": locator,
        "workspace_address": None,
        "declaration_hint": None,
        "unlock": None,
        "source": "core-ai-join-card",
    }


def parse_card(
    raw: bytes,
    *,
    limits: dict[str, int],
    sensitive_channel: bool,
) -> dict[str, Any]:
    try:
        card = parse_json_object(
            raw,
            label="join card",
            maximum=limits["card_bytes"],
            maximum_depth=limits["json_depth"],
            maximum_nodes=limits["json_nodes"],
        )
    except ValueError:
        raise InputError() from None
    if card.get("kind") == CORE_AI_CARD_KIND:
        return _parse_core_ai_join_card(card)
    allowed = {
        "schema",
        "locator",
        "workspace_address",
        "declaration",
        "unlock_fragment",
    }
    if (
        set(card) - allowed
        or card.get("schema") not in CARD_SCHEMAS
        or not isinstance(card.get("locator"), str)
    ):
        raise InputError()
    unlock = card.pop("unlock_fragment", None)
    if unlock is not None:
        if not sensitive_channel:
            raise InputError()
        unlock = _text(unlock, maximum=512)
    locator = _text(card["locator"], maximum=2048)
    workspace = card.get("workspace_address")
    if workspace is not None:
        workspace = _text(workspace, maximum=2048)
    hint = card.get("declaration")
    if hint is not None:
        if isinstance(hint, dict) and hint.get("schema") == DECLARATION_SCHEMA:
            hint = validate_declaration(hint, limits=limits)
        else:
            hint = _validate_static_reference(hint, limits)
    card.clear()
    return {
        "locator": locator,
        "workspace_address": workspace,
        "declaration_hint": hint,
        "unlock": unlock,
        "source": "card-stdin" if sensitive_channel else "card-json",
    }


def parse_request_input(
    args: argparse.Namespace,
    *,
    limits: dict[str, int],
    cwd: Path,
) -> dict[str, Any]:
    supplied = sum(
        value is not None
        for value in (args.locator, args.card_json)
    ) + int(args.card_stdin)
    if supplied != 1:
        raise InputError()
    if args.card_stdin:
        raw = sys.stdin.buffer.read(limits["card_bytes"] + 1)
        request = parse_card(raw, limits=limits, sensitive_channel=True)
    elif args.card_json is not None:
        request = parse_card(
            args.card_json.encode("utf-8"),
            limits=limits,
            sensitive_channel=False,
        )
    else:
        locator = _text(args.locator, maximum=2048)
        if locator.startswith("hive://"):
            raise InputError()
        request = {
            "locator": locator,
            "workspace_address": None,
            "declaration_hint": None,
            "unlock": None,
            "source": "locator",
        }
    locator = request["locator"]
    if locator.startswith("hive://"):
        if not args.card_stdin:
            raise InputError()
        local_locator, local_workspace, fragment = _parse_hive_url(locator)
        if request.get("unlock") is not None and fragment is not None:
            raise InputError()
        request["locator"] = local_locator
        request["workspace_address"] = (
            request.get("workspace_address") or local_workspace
        )
        request["unlock"] = request.get("unlock") or fragment
        fragment = None
        locator = local_locator
    cli_workspace = args.workspace_address
    if cli_workspace is not None:
        cli_workspace = _text(cli_workspace, maximum=2048)
        if (
            request.get("workspace_address") is not None
            and request["workspace_address"] != cli_workspace
        ):
            raise InputError()
        request["workspace_address"] = cli_workspace
    request["locator_descriptor"] = classify_locator(request["locator"], cwd)
    if request.get("workspace_address") is not None:
        request["workspace_descriptor"] = classify_locator(
            request["workspace_address"], cwd
        )
    else:
        request["workspace_descriptor"] = None
    request.pop("locator", None)
    return request


def _dial_record_body(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "id"}


def dial_record_id(record: dict[str, Any]) -> str:
    return "dial:sha256:" + digest(_dial_record_body(record))


def load_dialbook(path: Path, limits: dict[str, int]) -> list[dict[str, Any]]:
    try:
        raw = _read_regular(path, limits["dialbook_bytes"], storage=True)
        value = parse_json_object(
            raw,
            label="dialbook",
            maximum=limits["dialbook_bytes"],
            maximum_depth=limits["json_depth"],
            maximum_nodes=limits["json_nodes"],
        )
    except (ValueError, HubError):
        raise StorageError() from None
    if set(value) != {"schema", "records"} or value.get("schema") != DIALBOOK_SCHEMA:
        raise StorageError()
    records = value.get("records")
    if not isinstance(records, list) or len(records) > limits["dialbook_records"]:
        raise StorageError()
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) not in (
            {"id", "chants", "locator"},
            {"id", "chants", "locator", "workspace_address"},
            {"id", "chants", "locator", "declaration"},
            {
                "id",
                "chants",
                "locator",
                "workspace_address",
                "declaration",
            },
        ):
            raise StorageError()
        record_id = record.get("id")
        if (
            not isinstance(record_id, str)
            or DIAL_ID_RE.fullmatch(record_id) is None
            or record_id != dial_record_id(record)
            or record_id in seen
        ):
            raise StorageError()
        chants = record.get("chants")
        if (
            not isinstance(chants, list)
            or len(chants) > 16
            or any(not isinstance(item, str) for item in chants)
        ):
            raise StorageError()
        try:
            normalized_chants = sorted({normalize_chant(item) for item in chants})
        except InputError:
            raise StorageError() from None
        locator = record.get("locator")
        if not isinstance(locator, str) or not locator or len(locator.encode()) > 2048:
            raise StorageError()
        item = dict(record)
        item["chants"] = normalized_chants
        if "declaration" in item:
            try:
                item["declaration"] = _validate_static_reference(
                    item["declaration"],
                    limits,
                )
            except HubError:
                raise StorageError() from None
        normalized.append(item)
        seen.add(record_id)
    return normalized


def resolve_dial_locator(
    descriptor: dict[str, Any],
    *,
    dialbook: Path,
    limits: dict[str, int],
    cwd: Path,
) -> tuple[dict[str, Any], str | None, Any]:
    records = load_dialbook(dialbook, limits)
    if descriptor["kind"] == "dial-id":
        matches = [item for item in records if item["id"] == descriptor["value"]]
    else:
        matches = [
            item
            for item in records
            if descriptor["value"] in item["chants"]
        ]
    if not matches:
        raise UnreachableError()
    if len(matches) > 1:
        raise ChantCollisionError(
            details={"candidate_ids": sorted(item["id"] for item in matches)}
        )
    record = matches[0]
    if "declaration" in record:
        return descriptor, record.get("workspace_address"), record["declaration"]
    nested = classify_locator(record["locator"], cwd)
    if nested["kind"] in {"dial-id", "chant"}:
        raise StorageError()
    return nested, record.get("workspace_address"), record.get("declaration")


def _safe_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    kind = descriptor["kind"]
    if kind == "github":
        return {
            "kind": "github",
            "repository": descriptor["repository"],
            "branch": descriptor["branch"],
        }
    if kind == "local":
        return {
            "kind": "local",
            "path_sha256": hashlib.sha256(
                os.fsencode(descriptor["path"])
            ).hexdigest(),
        }
    return {"kind": kind, "value": descriptor.get("value")}


def target_digest(
    descriptor: dict[str, Any],
    workspace: dict[str, Any] | None,
) -> str:
    return digest(
        {
            "locator": _safe_descriptor(descriptor),
            "workspace": _safe_descriptor(workspace) if workspace else None,
        }
    )


def default_device_root(home: str | os.PathLike[str] | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".agent-storage" / "hive-hub" / "v1"


def device_root(raw: str | None, cwd: Path) -> Path:
    if raw is None:
        candidate = default_device_root()
    else:
        candidate = Path(os.path.expanduser(raw))
        if not candidate.is_absolute():
            raise InputError()
    try:
        return Path(os.path.abspath(candidate))
    except (OSError, ValueError):
        raise StorageError() from None


def _private_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        information = path.lstat()
        if (
            not stat.S_ISDIR(information.st_mode)
            or stat.S_ISLNK(information.st_mode)
            or os.name == "posix"
            and (
                information.st_uid != os.geteuid()
                or information.st_mode & 0o077
            )
        ):
            raise StorageError()
        if os.name == "posix":
            os.chmod(path, 0o700)
    except HubError:
        raise
    except OSError:
        raise StorageError() from None


def _ensure_storage(root: Path) -> None:
    _private_directory(root, create=True)
    marker = {
        "schema": "hive-hub-device/1",
        "version": "1",
        "private": True,
    }
    _write_json_once(root / "device.json", marker)


def _write_json_once(path: Path, value: dict[str, Any]) -> None:
    data = canonical_bytes(value) + b"\n"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private_directory(path.parent, create=False)
    if path.exists():
        current = _read_regular(path, len(data), storage=True)
        if current != data:
            raise StorageError()
        return
    temporary = path.parent / f".{path.name}.pending-{os.getpid()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            offset = 0
            while offset < len(data):
                written = os.write(descriptor, data[offset:])
                if written <= 0:
                    raise StorageError()
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    except HubError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise StorageError() from None


def _read_storage_json(path: Path, maximum: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = _read_regular(path, maximum, storage=True)
        return parse_json_object(
            raw,
            label="device record",
            maximum=maximum,
        )
    except (ValueError, HubError):
        raise StorageError() from None


def _plan(
    *,
    intent: str,
    target_sha256: str,
    binding_sha256: str | None,
    effects: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    value = {
        "schema": PLAN_SCHEMA,
        "intent": intent,
        "target_sha256": target_sha256,
        "binding_sha256": binding_sha256,
        "effects": effects,
        "approval": "exact-digest-only",
    }
    return value, digest(value)


def _planned_result(
    operation: str,
    plan: dict[str, Any],
    plan_digest: str,
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "operation": operation,
        "status": "planned",
        "ready": False,
        "plan_digest": plan_digest,
        "plan": plan,
    }


def _resolution_path(root: Path, target_sha256: str) -> Path:
    return root / "resolutions" / target_sha256 / "resolution.json"


def _resolve_plan(kind: str, target_sha256: str) -> tuple[dict[str, Any], str]:
    transport = (
        "adapter-native-git-acl"
        if kind == "github"
        else "pinned-static-json"
    )
    return _plan(
        intent="resolve-hive",
        target_sha256=target_sha256,
        binding_sha256=None,
        effects=[
            {
                "kind": "network-read",
                "transport": transport,
                "bounded": True,
                "credentials_output": False,
            },
            {
                "kind": "local-write",
                "purpose": "content-addressed inert resolution cache",
                "reversible": True,
            },
        ],
    )


def _join_plan(
    declaration: dict[str, Any],
    *,
    target_sha256: str,
    binding_sha256: str,
    implementation: str,
) -> tuple[dict[str, Any], str]:
    if implementation == "local-subscription":
        effects = [
            {
                "kind": "local-write",
                "purpose": "one local Hive subscription",
                "reversible": True,
            }
        ]
        intent = "save-subscription"
    else:
        effects = [
            {
                "kind": "network-read",
                "transport": "adapter-native-git-acl",
                "bounded": True,
                "credentials_output": False,
            },
            {
                "kind": "local-write",
                "purpose": "detached current-main and requested-branch worktrees",
                "reversible": True,
            },
            {
                "kind": "local-execute",
                "command": VERIFIED_JOIN_COMMAND,
                "downloaded_learning_executed": False,
                "remote_write": False,
            },
        ]
        intent = "join-with-verified-current-main"
    return _plan(
        intent=intent,
        target_sha256=target_sha256,
        binding_sha256=binding_sha256,
        effects=effects,
    )


def _adapter(
    declaration: dict[str, Any],
    lock: dict[str, Any],
) -> dict[str, Any]:
    requested = declaration["adapter"]
    for adapter in lock["adapters"]:
        if (
            adapter["id"] == requested["id"]
            and adapter["fingerprint"] == requested["fingerprint"]
        ):
            return adapter
    raise UnknownContractError(learning=declaration["learning"])


def _check_factor(declaration: dict[str, Any], unlock: str | None) -> None:
    access = declaration["access"]
    if access["mode"] != "acl+qr":
        return
    if (
        unlock is None
        or hashlib.sha256(unlock.encode("utf-8")).hexdigest()
        != access["unlock_sha256"]
    ):
        raise FactorError()


def _declaration_from_local(
    descriptor: dict[str, Any],
    *,
    lock: dict[str, Any],
    hint: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(descriptor["path"])
    if path.is_dir():
        candidates = [path / Path(relative) for relative in DECLARATION_PATHS]
        existing: list[Path] = []
        seen_files: set[tuple[int, int]] = set()
        for candidate in candidates:
            try:
                information = candidate.lstat()
            except OSError:
                continue
            identity = (information.st_dev, information.st_ino)
            if stat.S_ISREG(information.st_mode) and identity not in seen_files:
                existing.append(candidate)
                seen_files.add(identity)
        if len(existing) != 1:
            raise ContractError()
        declaration_path = existing[0]
    elif path.is_file():
        declaration_path = path
    else:
        raise UnreachableError()
    try:
        raw = _read_regular(declaration_path, lock["limits"]["json_bytes"])
        value = parse_json_object(
            raw,
            label="Hive declaration",
            maximum=lock["limits"]["json_bytes"],
            maximum_depth=lock["limits"]["json_depth"],
            maximum_nodes=lock["limits"]["json_nodes"],
        )
    except (ValueError, HubError):
        raise ContractError() from None
    declaration = validate_declaration(value, limits=lock["limits"])
    _check_declaration_hint(declaration, raw, hint, lock["limits"])
    return declaration, {
        "kind": "local",
        "declaration_sha256": digest(declaration),
        "source_path": str(declaration_path),
    }


def _check_declaration_hint(
    declaration: dict[str, Any],
    raw: bytes,
    hint: Any,
    limits: dict[str, int],
) -> None:
    if hint is None:
        return
    if isinstance(hint, dict) and hint.get("schema") == DECLARATION_SCHEMA:
        if canonical_bytes(hint) != canonical_bytes(declaration):
            raise ContractError()
        return
    reference = _validate_static_reference(hint, limits)
    if (
        len(raw) != reference["bytes"]
        or hashlib.sha256(raw).hexdigest() != reference["sha256"]
    ):
        raise ContractError()


def _git_config_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in (
        "APPDATA",
        "COMSPEC",
        "GH_CONFIG_DIR",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "USERPROFILE",
        "WINDIR",
        "XDG_CONFIG_HOME",
    ):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    return environment


def _credential_helpers(remote: str) -> list[str]:
    try:
        result = subprocess.run(
            [
                _git_executable(),
                "config",
                "--null",
                "--get-urlmatch",
                "credential.helper",
                remote,
            ],
            env=_git_config_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ExecutionError() from None
    if result.returncode not in {0, 1} or len(result.stdout) > 16 * 1025:
        raise ExecutionError()
    helpers: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            helper = raw.decode("utf-8")
        except UnicodeError:
            raise ExecutionError() from None
        if (
            len(raw) > 1024
            or "\x00" in helper
            or "\n" in helper
            or "\r" in helper
        ):
            raise ExecutionError()
        helpers.append(helper)
    if len(helpers) > 16:
        raise ExecutionError()
    return helpers


def _git_environment(*, network: bool) -> dict[str, str]:
    environment = _git_config_environment()
    environment.update(
        {
            "GCM_GUI_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "SSH_ASKPASS_REQUIRE": "never",
        }
    )
    if Path("/usr/bin/false").is_file():
        environment["GIT_ASKPASS"] = "/usr/bin/false"
        environment["SSH_ASKPASS"] = "/usr/bin/false"
    if not network:
        environment["GIT_NO_LAZY_FETCH"] = "1"
    return environment


def _git_executable() -> str:
    executable = shutil.which("git")
    if not executable:
        raise ExecutionError()
    return executable


def _git_options(*, network: bool, helpers: list[str]) -> list[str]:
    options = [
        "--no-pager",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.eol=lf",
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={SKILL_ROOT / '.disabled-git-hooks'}",
        "-c",
        "credential.interactive=never",
        "-c",
        "fetch.fsckObjects=true",
        "-c",
        "fetch.recurseSubmodules=false",
        "-c",
        "filter.lfs.process=",
        "-c",
        "filter.lfs.required=false",
        "-c",
        "filter.lfs.smudge=",
        "-c",
        "gc.auto=0",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "submodule.recurse=false",
        "-c",
        "transfer.fsckObjects=true",
    ]
    if os.environ.get("HIVE_HUB_LOCAL_TESTING") == "1":
        options.extend(["-c", "protocol.file.allow=always"])
    if network:
        options.extend(
            [
                "-c",
                "http.followRedirects=false",
                "-c",
                "http.sslVerify=true",
                "-c",
                "credential.helper=",
            ]
        )
        for helper in helpers:
            options.extend(["-c", f"credential.helper={helper}"])
    return options


def _run_git(
    arguments: list[str],
    *,
    cwd: Path | None,
    timeout: int,
    maximum: int,
    network: bool,
    helpers: list[str] | None = None,
) -> bytes:
    command = [
        _git_executable(),
        *_git_options(network=network, helpers=helpers or []),
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=_git_environment(network=network),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        if network:
            raise UnreachableError() from None
        raise ExecutionError() from None
    if result.returncode != 0:
        if network:
            raise UnreachableError()
        raise ExecutionError()
    if len(result.stdout) > maximum or len(result.stderr) > maximum:
        raise ExecutionError()
    return result.stdout


def _test_remote(address: dict[str, Any]) -> str:
    if os.environ.get("HIVE_HUB_LOCAL_TESTING") != "1":
        return address["remote"]
    override = os.environ.get("HIVE_HUB_TEST_GIT_REMOTE")
    if not override:
        return address["remote"]
    candidate = Path(override)
    if not candidate.is_absolute() or not candidate.exists():
        raise UnreachableError()
    return str(candidate)


def _advertised_oids(
    address: dict[str, Any],
    *,
    timeout: int,
    maximum: int,
    helpers: list[str],
) -> dict[str, str]:
    remote = _test_remote(address)
    references = ["refs/heads/main"]
    if address["branch"] != "main":
        references.append(f"refs/heads/{address['branch']}")
    raw = _run_git(
        ["ls-remote", "--refs", remote, *references],
        cwd=None,
        timeout=timeout,
        maximum=maximum,
        network=True,
        helpers=helpers,
    )
    found: dict[str, str] = {}
    try:
        for line in raw.decode("ascii").splitlines():
            oid, ref = line.split("\t", 1)
            if COMMIT_RE.fullmatch(oid) is None or ref not in references:
                raise ValueError
            found[ref] = oid
    except (UnicodeError, ValueError):
        raise UnreachableError() from None
    if set(found) != set(references):
        raise UnreachableError()
    return {
        "main": found["refs/heads/main"],
        "source": found[f"refs/heads/{address['branch']}"],
    }


def _repository_root(root: Path, address: dict[str, Any]) -> Path:
    key = hashlib.sha256(address["repository"].encode("utf-8")).hexdigest()
    return root / "repositories" / key


def _ensure_bare_cache(
    root: Path,
    address: dict[str, Any],
    *,
    timeout: int,
    maximum: int,
) -> Path:
    repository_root = _repository_root(root, address)
    _private_directory(repository_root, create=True)
    binding = {
        "schema": "hive-hub-repository-binding/1",
        "repository": address["repository"],
    }
    _write_json_once(repository_root / "binding.json", binding)
    cache = repository_root / "cache.git"
    remote = _test_remote(address)
    if not cache.exists():
        _run_git(
            ["init", "--bare", str(cache)],
            cwd=repository_root,
            timeout=timeout,
            maximum=maximum,
            network=False,
        )
        if os.name == "posix":
            try:
                os.chmod(cache, 0o700)
            except OSError:
                raise StorageError() from None
        _run_git(
            ["--git-dir", str(cache), "remote", "add", "origin", remote],
            cwd=repository_root,
            timeout=timeout,
            maximum=maximum,
            network=False,
        )
        _run_git(
            [
                "--git-dir",
                str(cache),
                "config",
                "remote.origin.promisor",
                "true",
            ],
            cwd=repository_root,
            timeout=timeout,
            maximum=maximum,
            network=False,
        )
        _run_git(
            [
                "--git-dir",
                str(cache),
                "config",
                "remote.origin.partialclonefilter",
                "blob:none",
            ],
            cwd=repository_root,
            timeout=timeout,
            maximum=maximum,
            network=False,
        )
    _private_directory(cache, create=False)
    configured = _run_git(
        ["--git-dir", str(cache), "remote", "get-url", "origin"],
        cwd=repository_root,
        timeout=timeout,
        maximum=4096,
        network=False,
    ).decode("utf-8", "strict").strip()
    if configured != remote:
        raise StorageError()
    return cache


def _fetch_refs(
    cache: Path,
    address: dict[str, Any],
    advertised: dict[str, str],
    *,
    timeout: int,
    maximum: int,
    helpers: list[str],
) -> None:
    refspecs = [
        "+refs/heads/main:refs/hive-hub/main",
    ]
    if address["branch"] == "main":
        refspecs.append("+refs/heads/main:refs/hive-hub/source")
    else:
        refspecs.append(
            f"+refs/heads/{address['branch']}:refs/hive-hub/source"
        )
    _run_git(
        [
            "--git-dir",
            str(cache),
            "fetch",
            "--no-tags",
            "--depth=1",
            "--filter=blob:none",
            "origin",
            *refspecs,
        ],
        cwd=cache.parent,
        timeout=timeout,
        maximum=maximum,
        network=True,
        helpers=helpers,
    )
    for role, ref in (("main", "refs/hive-hub/main"), ("source", "refs/hive-hub/source")):
        actual = _run_git(
            ["--git-dir", str(cache), "rev-parse", "--verify", ref],
            cwd=cache.parent,
            timeout=timeout,
            maximum=128,
            network=False,
        ).decode("ascii").strip()
        if actual != advertised[role]:
            raise UnreachableError()


def _git_blob(
    cache: Path,
    oid: str,
    relative: str,
    *,
    maximum: int,
    timeout: int,
    optional: bool = False,
    helpers: list[str] | None = None,
) -> bytes | None:
    safe = _safe_relative(relative).as_posix()
    try:
        try:
            blob = _run_git(
                ["--git-dir", str(cache), "rev-parse", f"{oid}:{safe}"],
                cwd=cache.parent,
                timeout=timeout,
                maximum=128,
                network=False,
            ).decode("ascii").strip()
        except ExecutionError:
            if optional:
                return None
            raise ContractError() from None
        if COMMIT_RE.fullmatch(blob) is None:
            raise ValueError
        size_text = _run_git(
            ["--git-dir", str(cache), "cat-file", "-s", blob],
            cwd=cache.parent,
            timeout=timeout,
            maximum=128,
            network=True,
            helpers=helpers,
        ).decode("ascii").strip()
        if not size_text.isdigit() or int(size_text) > maximum:
            raise ValueError
        data = _run_git(
            ["--git-dir", str(cache), "cat-file", "blob", blob],
            cwd=cache.parent,
            timeout=timeout,
            maximum=maximum,
            network=True,
            helpers=helpers,
        )
        if len(data) != int(size_text):
            raise ValueError
        return data
    except (UnicodeError, ValueError, ContractError):
        raise ContractError() from None


def _extract_contract_from_skill(raw: bytes, maximum: int) -> dict[str, Any] | None:
    if len(raw) > maximum:
        raise ContractError()
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise ContractError() from None
    if (
        VERIFIED_JOIN_CONTRACT_START not in text
        and VERIFIED_JOIN_CONTRACT_END not in text
    ):
        return None
    if (
        text.count(VERIFIED_JOIN_CONTRACT_START) != 1
        or text.count(VERIFIED_JOIN_CONTRACT_END) != 1
    ):
        raise ContractError()
    body = text.split(VERIFIED_JOIN_CONTRACT_START, 1)[1].split(
        VERIFIED_JOIN_CONTRACT_END, 1
    )[0]
    commands = re.findall(r"```sh[ \t]*\n(.*?)```", body, re.DOTALL)
    contracts = re.findall(r"```json[ \t]*\n(.*?)```", body, re.DOTALL)
    if len(commands) != 1 or commands[0].strip() != " ".join(
        VERIFIED_JOIN_COMMAND
    ):
        raise ContractError()
    if len(contracts) != 1:
        raise ContractError()
    try:
        return parse_json_object(
            contracts[0].encode("utf-8"),
            label="MicroSOL contract",
            maximum=maximum,
        )
    except ValueError:
        raise ContractError() from None


def _verified_join_contract_from_git(
    cache: Path,
    main_oid: str,
    *,
    lock: dict[str, Any],
    timeout: int,
    helpers: list[str],
) -> tuple[dict[str, Any], dict[str, bytes]] | None:
    files: dict[str, bytes] = {}
    contract_raw = _git_blob(
        cache,
        main_oid,
        "join-contract.json",
        maximum=lock["limits"]["json_bytes"],
        timeout=timeout,
        optional=True,
        helpers=helpers,
    )
    if contract_raw is None:
        return None
    files["join-contract.json"] = contract_raw
    try:
        contract = parse_json_object(
            files["join-contract.json"],
            label="MicroSOL join contract",
            maximum=lock["limits"]["json_bytes"],
        )
    except ValueError:
        raise ContractError() from None
    if canonical_bytes(contract) != canonical_bytes(
        lock["verified_join"]["contract"]
    ):
        return None
    for relative in (
        "SKILL.md",
        ".github/skills/microsol/SKILL.md",
        "HOME.md",
        "release-lock.json",
    ):
        data = _git_blob(
            cache,
            main_oid,
            relative,
            maximum=8 * 1024 * 1024,
            timeout=timeout,
            helpers=helpers,
        )
        assert data is not None
        files[relative] = data
    skill_contract = _extract_contract_from_skill(
        files["SKILL.md"], lock["limits"]["json_bytes"]
    )
    mirror_contract = _extract_contract_from_skill(
        files[".github/skills/microsol/SKILL.md"],
        lock["limits"]["json_bytes"],
    )
    home_contract = _extract_contract_from_skill(
        files["HOME.md"], lock["limits"]["json_bytes"]
    )
    embedded = [
        item for item in (skill_contract, mirror_contract, home_contract) if item is not None
    ]
    if embedded and any(
        canonical_bytes(item) != canonical_bytes(contract) for item in embedded
    ):
        raise ContractError()
    if files["SKILL.md"] != files[".github/skills/microsol/SKILL.md"]:
        raise ContractError()
    return contract, files


def _verified_join_declaration(
    *,
    lock: dict[str, Any],
    repository: str,
    main_oid: str,
    files: dict[str, bytes],
) -> dict[str, Any]:
    def artifact(role: str, relative: str, media_type: str) -> dict[str, Any]:
        data = files[relative]
        return {
            "role": role,
            "url": (
                f"https://raw.githubusercontent.com/{repository}/"
                f"{main_oid}/{quote(relative, safe='/')}"
            ),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "media_type": media_type,
        }

    artifacts = [
        artifact("spec", "join-contract.json", "application/json"),
        artifact("schema", "join-contract.json", "application/json"),
        artifact("examples", "SKILL.md", "text/markdown"),
        artifact("conformance", "release-lock.json", "application/json"),
        artifact("skill", "SKILL.md", "text/markdown"),
    ]
    learning_body = {
        "schema": "hive-hub-learning-bundle/1",
        "artifacts": artifacts,
    }
    adapter = next(
        item
        for item in lock["adapters"]
        if item["implementation"] == "verified-current-main"
    )
    protocol_sha = lock["verified_join"]["contract_sha256"]
    value = {
        "schema": DECLARATION_SCHEMA,
        "id": "dial:sha256:"
        + digest(
            {
                "repository": repository,
                "main": main_oid,
                "contract": protocol_sha,
            }
        ),
        "name": "Verified current-main Hive",
        "access": {"visibility": "private", "mode": "acl-only"},
        "protocol": {
            "id": "microsol-any-ai-setup/2",
            "fingerprint": protocol_sha,
            "spec_sha256": artifacts[0]["sha256"],
        },
        "adapter": {
            "id": adapter["id"],
            "fingerprint": adapter["fingerprint"],
        },
        "learning": {
            **learning_body,
            "sha256": digest(learning_body),
        },
        "conformance": {
            "id": "verified-release-lock/1",
            "artifact_sha256": artifacts[3]["sha256"],
        },
        "join": {
            "kind": "verified-current-main",
            "next_step": "Use verified current-main tooling against the preserved requested branch.",
        },
    }
    # The exact MicroSOL protocol fingerprint is its contract. The spec artifact
    # carries the same canonical JSON with a trailing newline, so bind the
    # protocol to the canonical contract while keeping the artifact hash exact.
    value["protocol"]["fingerprint"] = value["protocol"]["spec_sha256"]
    return validate_declaration(value, limits=lock["limits"])


def _generic_declaration_from_git(
    cache: Path,
    main_oid: str,
    *,
    lock: dict[str, Any],
    timeout: int,
    helpers: list[str],
) -> tuple[dict[str, Any], bytes, str]:
    found: list[tuple[str, bytes]] = []
    for relative in DECLARATION_PATHS:
        data = _git_blob(
            cache,
            main_oid,
            relative,
            maximum=lock["limits"]["json_bytes"],
            timeout=timeout,
            optional=True,
            helpers=helpers,
        )
        if data is None:
            continue
        found.append((relative, data))
    if len(found) != 1:
        raise ContractError()
    relative, raw = found[0]
    try:
        value = parse_json_object(
            raw,
            label="Hive declaration",
            maximum=lock["limits"]["json_bytes"],
            maximum_depth=lock["limits"]["json_depth"],
            maximum_nodes=lock["limits"]["json_nodes"],
        )
    except ValueError:
        raise ContractError() from None
    return validate_declaration(value, limits=lock["limits"]), raw, relative


def _resolve_github(
    descriptor: dict[str, Any],
    *,
    root: Path,
    lock: dict[str, Any],
    hint: Any,
    timeout: int,
) -> dict[str, Any]:
    helpers = _credential_helpers(descriptor["remote"])
    advertised = _advertised_oids(
        descriptor,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        helpers=helpers,
    )
    cache = _ensure_bare_cache(
        root,
        descriptor,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
    )
    _fetch_refs(
        cache,
        descriptor,
        advertised,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        helpers=helpers,
    )
    verified_join = _verified_join_contract_from_git(
        cache,
        advertised["main"],
        lock=lock,
        timeout=timeout,
        helpers=helpers,
    )
    if verified_join is not None:
        _, files = verified_join
        declaration = _verified_join_declaration(
            lock=lock,
            repository=descriptor["repository"],
            main_oid=advertised["main"],
            files=files,
        )
        raw = canonical_bytes(declaration)
        declaration_path = "join-contract.json"
    else:
        declaration, raw, declaration_path = _generic_declaration_from_git(
            cache,
            advertised["main"],
            lock=lock,
            timeout=timeout,
            helpers=helpers,
        )
    _check_declaration_hint(declaration, raw, hint, lock["limits"])
    return {
        "schema": "hive-hub-resolution/1",
        "target_sha256": target_digest(descriptor, None),
        "source": {
            "kind": "github",
            "repository": descriptor["repository"],
            "branch": descriptor["branch"],
            "main_oid": advertised["main"],
            "source_oid": advertised["source"],
            "declaration_path": declaration_path,
        },
        "declaration": declaration,
        "declaration_sha256": digest(declaration),
    }


def _fetch_pinned_json(
    reference: dict[str, Any],
    *,
    limits: dict[str, int],
    timeout: int,
) -> tuple[dict[str, Any], bytes]:
    reference = _validate_static_reference(reference, limits)
    request = Request(
        reference["url"],
        headers={
            "Accept": "application/json",
            "User-Agent": "hive-hub-skill/1",
        },
        method="GET",
    )
    try:
        response = build_opener(_NoRedirect).open(request, timeout=timeout)
        with response:
            raw = response.read(reference["bytes"] + 1)
    except HubError:
        raise
    except Exception:
        raise UnreachableError() from None
    if (
        len(raw) != reference["bytes"]
        or hashlib.sha256(raw).hexdigest() != reference["sha256"]
    ):
        raise ContractError()
    try:
        value = parse_json_object(
            raw,
            label="pinned static declaration",
            maximum=limits["json_bytes"],
            maximum_depth=limits["json_depth"],
            maximum_nodes=limits["json_nodes"],
        )
    except ValueError:
        raise ContractError() from None
    return validate_declaration(value, limits=limits), raw


def _resolve_static(
    reference: dict[str, Any],
    *,
    descriptor: dict[str, Any],
    lock: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    declaration, _ = _fetch_pinned_json(
        reference,
        limits=lock["limits"],
        timeout=timeout,
    )
    return {
        "schema": "hive-hub-resolution/1",
        "target_sha256": target_digest(descriptor, None),
        "source": {
            "kind": "pinned-static-json",
            "reference": reference,
        },
        "declaration": declaration,
        "declaration_sha256": digest(declaration),
    }


def _binding_digest(
    resolution: dict[str, Any],
    workspace: dict[str, Any] | None,
) -> str:
    source = resolution["source"]
    binding: dict[str, Any] = {
        "declaration_sha256": resolution["declaration_sha256"],
        "workspace": _safe_descriptor(workspace) if workspace else None,
        "source_kind": source["kind"],
    }
    if source["kind"] == "github":
        binding["main_oid"] = source["main_oid"]
        binding["source_oid"] = source["source_oid"]
        binding["branch"] = source["branch"]
    return digest(binding)


def _resolution_from_local(
    descriptor: dict[str, Any],
    *,
    lock: dict[str, Any],
    hint: Any,
    workspace: dict[str, Any] | None,
) -> dict[str, Any]:
    declaration, context = _declaration_from_local(
        descriptor,
        lock=lock,
        hint=hint,
    )
    return {
        "schema": "hive-hub-resolution/1",
        "target_sha256": target_digest(descriptor, workspace),
        "source": context,
        "declaration": declaration,
        "declaration_sha256": digest(declaration),
    }


def _resolution_cache(
    root: Path,
    target_sha256: str,
    *,
    lock: dict[str, Any],
) -> dict[str, Any] | None:
    value = _read_storage_json(
        _resolution_path(root, target_sha256),
        2 * lock["limits"]["json_bytes"],
    )
    if value is None:
        return None
    if (
        value.get("schema") != "hive-hub-resolution/1"
        or value.get("target_sha256") != target_sha256
        or not isinstance(value.get("source"), dict)
        or not isinstance(value.get("declaration"), dict)
        or value.get("declaration_sha256") != digest(value["declaration"])
    ):
        raise StorageError()
    value["declaration"] = validate_declaration(
        value["declaration"], limits=lock["limits"]
    )
    return value


def _save_resolution(
    root: Path,
    target_sha256: str,
    resolution: dict[str, Any],
) -> None:
    if resolution["target_sha256"] != target_sha256:
        # A resolution built before an optional workspace was applied is rebound
        # to that safe request identity without changing its declaration.
        resolution = dict(resolution)
        resolution["target_sha256"] = target_sha256
    _write_json_once(_resolution_path(root, target_sha256), resolution)


def _subscription_record(
    declaration: dict[str, Any],
    *,
    descriptor: dict[str, Any],
    workspace: dict[str, Any] | None,
    binding_sha256: str,
) -> dict[str, Any]:
    locator: dict[str, Any]
    if descriptor["kind"] == "github":
        locator = {
            "kind": "github",
            "repository": descriptor["repository"],
            "branch": descriptor["branch"],
        }
    elif descriptor["kind"] == "local":
        locator = {"kind": "local", "path": descriptor["path"]}
    else:
        locator = _safe_descriptor(descriptor)
    workspace_value: dict[str, Any] | None
    if workspace is None:
        workspace_value = None
    elif workspace["kind"] == "local":
        workspace_value = {"kind": "local", "path": workspace["path"]}
    elif workspace["kind"] == "github":
        workspace_value = {
            "kind": "github",
            "repository": workspace["repository"],
            "branch": workspace["branch"],
        }
    else:
        workspace_value = _safe_descriptor(workspace)
    return {
        "schema": "hive-hub-subscription/1",
        "dial_record_id": declaration["id"],
        "name": declaration["name"],
        "protocol": declaration["protocol"],
        "adapter": declaration["adapter"],
        "declaration_sha256": digest(declaration),
        "binding_sha256": binding_sha256,
        "locator": locator,
        "workspace": workspace_value,
        "factor_verified": declaration["access"]["mode"] == "acl+qr",
    }


def _save_subscription(root: Path, record: dict[str, Any]) -> str:
    receipt = digest(record)
    _write_json_once(root / "subscriptions" / f"{receipt}.json", record)
    return receipt


def _verify_release_file(root: Path, relative: str, record: dict[str, Any]) -> None:
    path = root / _safe_relative(relative)
    if (
        not isinstance(record, dict)
        or set(record) != {"bytes", "sha256"}
        or type(record.get("bytes")) is not int
        or not 0 <= record["bytes"] <= 32 * 1024 * 1024
        or SHA256_RE.fullmatch(str(record.get("sha256"))) is None
    ):
        raise ContractError()
    data = _read_regular(path, record["bytes"])
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ContractError()


def _verify_join_release(root: Path, lock: dict[str, Any]) -> None:
    listed_raw = _read_regular(
        root / "RELEASE-FILES.txt", lock["limits"]["git_output_bytes"]
    )
    try:
        listed_text = listed_raw.decode("utf-8")
    except UnicodeError:
        raise ContractError() from None
    if not listed_raw.endswith(b"\n") or b"\r" in listed_raw:
        raise ContractError()
    listed = listed_text.splitlines()
    if (
        not listed
        or len(listed) > 10_000
        or listed != sorted(set(listed))
        or not VERIFIED_JOIN_REQUIRED_FILES.issubset(listed)
    ):
        raise ContractError()
    actual: list[str] = []
    for path in sorted(root.rglob("*")):
        relative_parts = path.relative_to(root).parts
        if relative_parts and relative_parts[0] in {".git", ".microsol"}:
            continue
        relative = path.relative_to(root).as_posix()
        information = path.lstat()
        if stat.S_ISLNK(information.st_mode):
            raise ContractError()
        if stat.S_ISREG(information.st_mode):
            actual.append(relative)
        elif not stat.S_ISDIR(information.st_mode):
            raise ContractError()
    if listed != actual:
        raise ContractError()
    release_raw = _read_regular(root / "release-lock.json", 8 * 1024 * 1024)
    try:
        release = parse_json_object(
            release_raw,
            label="MicroSOL release lock",
            maximum=8 * 1024 * 1024,
        )
    except ValueError:
        raise ContractError() from None
    if (
        set(release) != {"schema", "role", "authority", "files"}
        or release.get("schema") != "microsol-release-lock/1"
        or release.get("role") != "evidence"
        or release.get("authority") is not False
        or not isinstance(release.get("files"), dict)
    ):
        raise ContractError()
    expected = set(listed) - {
        "release-lock.json",
        "workspaces/workspace-lock.json",
    }
    if set(release["files"]) != expected:
        raise ContractError()
    for relative in sorted(expected):
        _verify_release_file(root, relative, release["files"][relative])
    contract_raw = _read_regular(
        root / "join-contract.json", lock["limits"]["json_bytes"]
    )
    try:
        contract = parse_json_object(
            contract_raw,
            label="MicroSOL join contract",
            maximum=lock["limits"]["json_bytes"],
        )
    except ValueError:
        raise ContractError() from None
    if canonical_bytes(contract) != canonical_bytes(
        lock["verified_join"]["contract"]
    ):
        raise ContractError()


def _worktree(
    cache: Path,
    repository_root: Path,
    *,
    role: str,
    oid: str,
    timeout: int,
    maximum: int,
    helpers: list[str],
) -> Path:
    target = repository_root / "worktrees" / role / oid
    _private_directory(target.parent, create=True)
    if not target.exists():
        _run_git(
            [
                "--git-dir",
                str(cache),
                "worktree",
                "add",
                "--detach",
                str(target),
                oid,
            ],
            cwd=repository_root,
            timeout=timeout,
            maximum=maximum,
            network=True,
            helpers=helpers,
        )
    head = _run_git(
        ["-C", str(target), "rev-parse", "HEAD"],
        cwd=repository_root,
        timeout=timeout,
        maximum=128,
        network=False,
    ).decode("ascii").strip()
    symbolic = subprocess.run(
        [
            _git_executable(),
            *_git_options(network=False, helpers=[]),
            "-C",
            str(target),
            "symbolic-ref",
            "-q",
            "HEAD",
        ],
        env=_git_environment(network=False),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    status = _run_git(
        ["-C", str(target), "status", "--porcelain", "--untracked-files=no"],
        cwd=repository_root,
        timeout=timeout,
        maximum=maximum,
        network=False,
    )
    if head != oid or symbolic.returncode == 0 or status:
        raise StorageError()
    return target


def _run_json_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
    maximum: int,
) -> tuple[int, dict[str, Any]]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ExecutionError() from None
    if len(result.stdout) > maximum or len(result.stderr) > maximum:
        raise ExecutionError()
    try:
        value = parse_json_object(
            result.stdout,
            label="adapter result",
            maximum=maximum,
        )
    except ValueError:
        raise ExecutionError() from None
    return result.returncode, value


def _safe_user_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError()
    allowed = {
        "status",
        "message",
        "workspace",
        "hives",
        "pods",
        "next_board_item",
        "blocker",
        "display_text",
        "text_is_inert",
    }
    if set(value) - allowed:
        raise ExecutionError()
    _assert_no_sensitive_output(value)
    encoded = canonical_bytes(value)
    if len(encoded) > 16 * 1024:
        raise ExecutionError()
    return value


def _verified_join_environment(root: Path) -> dict[str, str]:
    environment = _git_environment(network=False)
    state = root / "state"
    _private_directory(state, create=True)
    environment.update(
        {
            "MICROSOL_HIVE_SUBSCRIPTIONS": str(state / "subscriptions"),
            "XDG_STATE_HOME": str(state),
        }
    )
    return environment


def _apply_verified_join(
    *,
    root: Path,
    descriptor: dict[str, Any],
    resolution: dict[str, Any],
    lock: dict[str, Any],
    timeout: int,
    workspace: dict[str, Any] | None,
    binding_sha256: str,
) -> dict[str, Any]:
    source = resolution["source"]
    if (
        descriptor.get("kind") != "github"
        or source.get("kind") != "github"
        or source.get("repository") != descriptor.get("repository")
        or source.get("branch") != descriptor.get("branch")
        or COMMIT_RE.fullmatch(str(source.get("main_oid"))) is None
        or COMMIT_RE.fullmatch(str(source.get("source_oid"))) is None
    ):
        raise ContractError()
    repository_root = _repository_root(root, descriptor)
    cache = repository_root / "cache.git"
    if not cache.is_dir():
        raise StorageError()
    helpers = _credential_helpers(descriptor["remote"])
    main = _worktree(
        cache,
        repository_root,
        role="main",
        oid=source["main_oid"],
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        helpers=helpers,
    )
    requested = _worktree(
        cache,
        repository_root,
        role="source",
        oid=source["source_oid"],
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        helpers=helpers,
    )
    _verify_join_release(main, lock)
    environment = _verified_join_environment(root)
    python = sys.executable
    verify_code, verification = _run_json_process(
        [python, "-B", str(main / "microsol.py"), "verify"],
        cwd=main,
        environment=environment,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
    )
    if (
        verify_code != 0
        or verification.get("ok") is not True
        or verification.get("network_contacted") is not False
    ):
        raise ExecutionError()
    before = _run_git(
        ["-C", str(requested), "status", "--porcelain", "--untracked-files=no"],
        cwd=repository_root,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        network=False,
    )
    returncode, result = _run_json_process(
        [python, "-B", str(main / "microsol.py"), "setup"],
        cwd=requested,
        environment=environment,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
    )
    after = _run_git(
        ["-C", str(requested), "status", "--porcelain", "--untracked-files=no"],
        cwd=repository_root,
        timeout=timeout,
        maximum=lock["limits"]["git_output_bytes"],
        network=False,
    )
    if before or after:
        raise ExecutionError()
    ready_contract = lock["verified_join"]["contract"]["ready"]
    if returncode != 0 or any(result.get(key) != value for key, value in ready_contract.items()):
        prerequisites = lock["verified_join"]["contract"]["prerequisites"]
        if all(result.get(key) == value for key, value in prerequisites.items()):
            raise ExecutionError(
                details={"reason": "prerequisites-required"}
            )
        raise ExecutionError()
    if source["source_oid"] != source["main_oid"]:
        required = {
            "action": "update",
            "source_commit": source["source_oid"],
            "target_release_commit": source["main_oid"],
            "source_unchanged": True,
            "old_branch_unchanged": True,
            "no_force_rebase_or_reset": True,
            "private_histories_copied": False,
            "private_keys_copied": False,
        }
        if any(result.get(key) != value for key, value in required.items()):
            raise ExecutionError()
    summary = _safe_user_summary(result.get("user_summary"))
    record = _subscription_record(
        resolution["declaration"],
        descriptor=descriptor,
        workspace=workspace,
        binding_sha256=binding_sha256,
    )
    receipt = _save_subscription(root, record)
    return {
        "schema": RESULT_SCHEMA,
        "operation": "join",
        "status": "ready",
        "ready": True,
        "adapter": resolution["declaration"]["adapter"]["id"],
        "current_main_tooling": True,
        "requested_branch_preserved": True,
        "local_subscription_sha256": receipt,
        "user_summary": summary,
    }


def _apply_subscription(
    *,
    root: Path,
    descriptor: dict[str, Any],
    workspace: dict[str, Any] | None,
    declaration: dict[str, Any],
    binding_sha256: str,
    operation: str,
) -> dict[str, Any]:
    record = _subscription_record(
        declaration,
        descriptor=descriptor,
        workspace=workspace,
        binding_sha256=binding_sha256,
    )
    receipt = _save_subscription(root, record)
    return {
        "schema": RESULT_SCHEMA,
        "operation": operation,
        "status": "ready",
        "ready": True,
        "adapter": declaration["adapter"]["id"],
        "local_subscription_sha256": receipt,
        "user_summary": {
            "status": "ready",
            "message": f"Subscribed to {declaration['name']}.",
            "next_step": declaration["join"]["next_step"],
            "text_is_inert": True,
        },
    }


def _decode_result(
    operation: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    descriptor = request["locator_descriptor"]
    return {
        "schema": RESULT_SCHEMA,
        "operation": operation,
        "status": "decoded",
        "ready": False,
        "locator": _safe_descriptor(descriptor),
        "workspace": (
            _safe_descriptor(request["workspace_descriptor"])
            if request["workspace_descriptor"]
            else None
        ),
        "card_source": request["source"],
        "has_optional_factor": bool(request.get("has_optional_factor")),
        "external_effects": [],
    }


def _dialbook_path(raw: str | None, cwd: Path) -> Path:
    if raw is None:
        return SKILL_ROOT / "registry" / "public-dialbook.json"
    candidate = Path(os.path.expanduser(raw))
    if not candidate.is_absolute():
        raise InputError()
    return Path(os.path.abspath(candidate))


def execute(args: argparse.Namespace, lock: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    cwd = Path(os.path.abspath(Path.cwd()))
    if args.operation == "verify":
        if any(
            (
                args.locator,
                args.card_json,
                args.card_stdin,
                args.workspace_address,
                args.dialbook,
                args.device_root,
                args.apply,
            )
        ):
            raise InputError()
        return 0, {
            "schema": RESULT_SCHEMA,
            "operation": "verify",
            "status": "verified",
            "ready": True,
            "skill": "hive-hub",
            "version": lock["version"],
            "stdlib_only": True,
            "isolated": bool(sys.flags.isolated),
            "files_verified": len(lock["files"]),
        }
    request = parse_request_input(args, limits=lock["limits"], cwd=cwd)
    descriptor = request["locator_descriptor"]
    if args.operation == "decode":
        if args.apply is not None or args.device_root is not None or args.dialbook is not None:
            raise InputError()
        request["has_optional_factor"] = request.get("unlock") is not None
        request["unlock"] = None
        return 0, _decode_result("decode", request)
    dialbook_hint = None
    dialbook_workspace = None
    direct_static_id = (
        descriptor["kind"] == "dial-id"
        and isinstance(request.get("declaration_hint"), dict)
        and "url" in request["declaration_hint"]
    )
    if descriptor["kind"] in {"dial-id", "chant"} and not direct_static_id:
        descriptor, dialbook_workspace, dialbook_hint = resolve_dial_locator(
            descriptor,
            dialbook=_dialbook_path(args.dialbook, cwd),
            limits=lock["limits"],
            cwd=cwd,
        )
        request["locator_descriptor"] = descriptor
        if request["workspace_descriptor"] is None and dialbook_workspace is not None:
            request["workspace_descriptor"] = classify_locator(
                dialbook_workspace, cwd
            )
        if request["declaration_hint"] is None:
            request["declaration_hint"] = dialbook_hint
    elif args.dialbook is not None:
        raise InputError()
    root = device_root(args.device_root, cwd)
    workspace = request["workspace_descriptor"]
    target_sha256 = target_digest(descriptor, workspace)
    resolution: dict[str, Any] | None = None
    remote_kind: str | None = None
    static_reference: dict[str, Any] | None = None
    if descriptor["kind"] == "local":
        resolution = _resolution_from_local(
            descriptor,
            lock=lock,
            hint=request["declaration_hint"],
            workspace=workspace,
        )
    elif descriptor["kind"] == "github":
        remote_kind = "github"
    elif request["declaration_hint"] is not None and isinstance(
        request["declaration_hint"], dict
    ) and "url" in request["declaration_hint"]:
        remote_kind = "static"
        static_reference = request["declaration_hint"]
    else:
        raise UnreachableError()
    if remote_kind is not None:
        resolution = _resolution_cache(
            root,
            target_sha256,
            lock=lock,
        )
        if resolution is None:
            plan, plan_sha = _resolve_plan(remote_kind, target_sha256)
            if args.apply is None:
                request["unlock"] = None
                return 0, _planned_result(args.operation, plan, plan_sha)
            if args.apply != plan_sha:
                raise PlanError()
            _ensure_storage(root)
            if remote_kind == "github":
                resolution = _resolve_github(
                    descriptor,
                    root=root,
                    lock=lock,
                    hint=request["declaration_hint"],
                    timeout=args.timeout,
                )
            else:
                assert static_reference is not None
                resolution = _resolve_static(
                    static_reference,
                    descriptor=descriptor,
                    lock=lock,
                    timeout=args.timeout,
                )
            _save_resolution(root, target_sha256, resolution)
            declaration = resolution["declaration"]
            _check_factor(declaration, request.get("unlock"))
            adapter = _adapter(declaration, lock)
            binding_sha256 = _binding_digest(resolution, workspace)
            next_plan, next_sha = _join_plan(
                declaration,
                target_sha256=target_sha256,
                binding_sha256=binding_sha256,
                implementation=adapter["implementation"],
            )
            request["unlock"] = None
            return 0, _planned_result(args.operation, next_plan, next_sha)
    assert resolution is not None
    declaration = validate_declaration(
        resolution["declaration"], limits=lock["limits"]
    )
    _check_factor(declaration, request.get("unlock"))
    request["unlock"] = None
    adapter = _adapter(declaration, lock)
    binding_sha256 = _binding_digest(resolution, workspace)
    plan, plan_sha = _join_plan(
        declaration,
        target_sha256=target_sha256,
        binding_sha256=binding_sha256,
        implementation=adapter["implementation"],
    )
    if args.apply is None:
        return 0, _planned_result(args.operation, plan, plan_sha)
    if args.apply != plan_sha:
        raise PlanError()
    _ensure_storage(root)
    if adapter["implementation"] == "local-subscription":
        return 0, _apply_subscription(
            root=root,
            descriptor=descriptor,
            workspace=workspace,
            declaration=declaration,
            binding_sha256=binding_sha256,
            operation=args.operation,
        )
    if adapter["implementation"] == "verified-current-main":
        return 0, _apply_verified_join(
            root=root,
            descriptor=descriptor,
            resolution=resolution,
            lock=lock,
            timeout=args.timeout,
            workspace=workspace,
            binding_sha256=binding_sha256,
        )
    raise UnknownContractError(learning=declaration["learning"])


def _assert_no_sensitive_output(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if (
                    SENSITIVE_KEY_RE.search(str(key))
                    and child is not False
                    and child is not None
                    and child != "none"
                ):
                    raise ExecutionError()
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str):
            if SECRET_VALUE_RE.search(current):
                raise ExecutionError()
            parsed = urlsplit(current) if "://" in current else None
            if parsed is not None and (
                parsed.username is not None or parsed.password is not None
            ):
                raise ExecutionError()


def emit(value: dict[str, Any]) -> None:
    _assert_no_sensitive_output(value)
    sys.stdout.write(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def parser() -> argparse.ArgumentParser:
    root = LockedArgumentParser(description=__doc__)
    root.add_argument("operation", nargs="?", default="verify", choices=OPERATIONS)
    root.add_argument("--locator")
    root.add_argument("--card-json")
    root.add_argument("--card-stdin", action="store_true")
    root.add_argument("--workspace-address")
    root.add_argument("--dialbook")
    root.add_argument("--device-root")
    root.add_argument("--apply")
    root.add_argument("--timeout", type=int, default=120)
    return root


def _validate_arguments(args: argparse.Namespace) -> None:
    if not 1 <= args.timeout <= 600:
        raise InputError()
    if args.apply is not None and SHA256_RE.fullmatch(args.apply) is None:
        raise PlanError()
    if args.operation == "decode" and args.timeout != 120:
        raise InputError()


def main(argv: list[str] | None = None) -> int:
    operation = "unknown"
    try:
        if sys.version_info < (3, 11) or not sys.flags.isolated:
            raise PackageError()
        lock = load_lock()
        args = parser().parse_args(argv)
        operation = args.operation
        _validate_arguments(args)
        code, value = execute(args, lock)
    except HubError as exc:
        emit(exc.result(operation))
        return 2
    emit(value)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
