"""Local filesystem workspace adapter using only the caller's OS access."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    contract_document,
    require,
)

FILESYSTEM_PROTOCOL = "hive-hub-local-workspace/1.0"
_FILESYSTEM_CONTRACT = {
    "schema": FILESYSTEM_PROTOCOL,
    "locator": "local-directory-or-file-uri",
    "access": "existing-os-permissions",
    "creates": False,
    "lists_contents": False,
}
FILESYSTEM_FINGERPRINT, FILESYSTEM_LEARNING = contract_document(
    FILESYSTEM_PROTOCOL,
    _FILESYSTEM_CONTRACT,
    source="embedded:hive-hub/local-workspace/1.0",
)
FILESYSTEM_DECLARATION = AdapterDeclaration(
    adapter_id="local-filesystem-workspace",
    fingerprint=FILESYSTEM_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "filesystem-read",
            RequirementLevel.REQUIRED,
            "The workspace must be readable and searchable by the current OS user.",
        ),
        CapabilityRequirement(
            "credential-broker",
            RequirementLevel.FORBIDDEN,
            "The adapter never obtains or changes OS credentials.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "Local probing performs no remote operation.",
        ),
    ),
    private_access_modes=(PrivateAccessMode.EXISTING_OS_ACCESS,),
    learning_bundle=FILESYSTEM_LEARNING,
    conformance=ConformanceContract(
        profile="hive-hub-local-workspace-conformance/1.0",
        fixtures=("adapters/fixtures/filesystem_workspace",),
        assertions=(
            "existing-directory-reachable",
            "missing-directory-unreachable",
            "no-directory-creation",
            "no-content-enumeration",
        ),
    ),
    authority_model="The operating system's existing filesystem permissions are authoritative.",
)


@dataclass(frozen=True)
class LocalWorkspaceAddress:
    path: Path

    @property
    def canonical_uri(self) -> str:
        return self.path.as_uri()


def parse_workspace_address(value: str | os.PathLike[str]) -> LocalWorkspaceAddress:
    raw = os.fspath(value)
    require(
        bool(raw) and "\0" not in raw,
        "invalid-workspace-address",
        "A local workspace address must be a non-empty path.",
    )
    if raw.startswith("file:"):
        parsed = urlsplit(raw)
        require(
            parsed.scheme == "file"
            and parsed.netloc in {"", "localhost"}
            and not parsed.query
            and not parsed.fragment,
            "invalid-workspace-address",
            "Only local file URIs are supported.",
        )
        raw = unquote(parsed.path)
    path = Path(raw).expanduser().resolve(strict=False)
    return LocalWorkspaceAddress(path)


@dataclass(frozen=True)
class LocalWorkspaceProbe:
    address: LocalWorkspaceAddress
    outcome: AccessOutcome
    readable: bool
    writable: bool
    existing_os_access: bool = True
    mutated: bool = False


class LocalFilesystemWorkspaceAdapter:
    declaration = FILESYSTEM_DECLARATION

    def parse(self, value: str | os.PathLike[str]) -> LocalWorkspaceAddress:
        return parse_workspace_address(value)

    def probe(
        self,
        address: str | os.PathLike[str] | LocalWorkspaceAddress,
    ) -> LocalWorkspaceProbe:
        parsed = (
            address
            if isinstance(address, LocalWorkspaceAddress)
            else parse_workspace_address(address)
        )
        path = parsed.path
        readable = (
            path.exists() and path.is_dir() and os.access(path, os.R_OK | os.X_OK)
        )
        writable = readable and os.access(path, os.W_OK)
        return LocalWorkspaceProbe(
            address=parsed,
            outcome=(
                AccessOutcome.REACHABLE if readable else AccessOutcome.UNREACHABLE
            ),
            readable=readable,
            writable=writable,
        )
