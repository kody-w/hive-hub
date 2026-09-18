"""Shared typed contracts for protocol-neutral Hive Hub adapters."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

_PROTOCOL_RE = re.compile(r"[a-z0-9][a-z0-9._/-]{0,127}\Z", re.ASCII)
_ADAPTER_ID_RE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z", re.ASCII)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class AdapterRefusal(ValueError):
    """A fail-closed adapter refusal with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise AdapterRefusal(code, message)


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AdapterRefusal(
            "invalid-contract-json",
            "The adapter contract is not canonical JSON data.",
        ) from error


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class RequirementLevel(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    FORBIDDEN = "forbidden"


class PrivateAccessMode(str, Enum):
    PUBLIC = "public"
    ACL_ONLY = "acl-only"
    ACL_PLUS_QR = "acl+qr"
    EXISTING_OS_ACCESS = "existing-os-access"
    DELEGATED = "delegated"
    LOCAL_INERT = "local-inert"


class AccessOutcome(str, Enum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    INERT = "inert"


@dataclass(frozen=True)
class ProtocolFingerprint:
    """An exact protocol identifier bound to canonical contract bytes."""

    protocol: str
    contract_sha256: str

    def __post_init__(self) -> None:
        require(
            _PROTOCOL_RE.fullmatch(self.protocol) is not None,
            "invalid-protocol",
            "Protocol identifiers use lowercase protocol/version labels.",
        )
        require(
            _SHA256_RE.fullmatch(self.contract_sha256) is not None,
            "invalid-protocol-fingerprint",
            "Protocol contract fingerprints must be lowercase SHA-256 values.",
        )

    @property
    def value(self) -> str:
        return f"{self.protocol}#sha256:{self.contract_sha256}"

    @classmethod
    def from_contract(
        cls,
        protocol: str,
        contract: object,
    ) -> ProtocolFingerprint:
        return cls(protocol, sha256_bytes(canonical_json(contract)))

    @classmethod
    def parse(cls, value: str) -> ProtocolFingerprint:
        require(
            type(value) is str and value.count("#sha256:") == 1,
            "invalid-protocol-fingerprint",
            "Protocol fingerprints use <protocol>#sha256:<digest>.",
        )
        protocol, digest = value.split("#sha256:", 1)
        return cls(protocol, digest)


@dataclass(frozen=True)
class CapabilityRequirement:
    capability: str
    level: RequirementLevel
    rationale: str

    def __post_init__(self) -> None:
        require(
            _ADAPTER_ID_RE.fullmatch(self.capability) is not None,
            "invalid-capability",
            "Capability names use lowercase kebab-case.",
        )
        require(
            bool(self.rationale.strip()),
            "invalid-capability",
            "Capability requirements need a rationale.",
        )


@dataclass(frozen=True)
class LearningDocument:
    """Embedded protocol-learning text that is always treated as inert data."""

    name: str
    media_type: str
    source: str
    content: str
    sha256: str
    executable: bool = False

    def __post_init__(self) -> None:
        require(
            bool(self.name.strip()) and bool(self.media_type.strip()),
            "invalid-learning-document",
            "Learning documents require a name and media type.",
        )
        require(
            self.executable is False,
            "executable-learning-document",
            "Adapter learning documents must remain inert.",
        )
        require(
            sha256_bytes(self.content.encode("utf-8")) == self.sha256,
            "learning-document-digest",
            "Learning document bytes do not match their SHA-256.",
        )

    @classmethod
    def embedded(
        cls,
        *,
        name: str,
        media_type: str,
        source: str,
        content: str,
    ) -> LearningDocument:
        return cls(
            name=name,
            media_type=media_type,
            source=source,
            content=content,
            sha256=sha256_bytes(content.encode("utf-8")),
        )


@dataclass(frozen=True)
class LearningBundle:
    schema: str
    documents: tuple[LearningDocument, ...]
    treatment: str = "inert-data"

    def __post_init__(self) -> None:
        require(
            self.schema == "hive-hub-learning-bundle/1.0",
            "invalid-learning-bundle",
            "Unknown learning bundle schema.",
        )
        require(
            bool(self.documents),
            "invalid-learning-bundle",
            "Every adapter must declare at least one learning document.",
        )
        require(
            self.treatment == "inert-data",
            "invalid-learning-bundle",
            "Learning bundles must be inert.",
        )


@dataclass(frozen=True)
class ConformanceContract:
    profile: str
    fixtures: tuple[str, ...]
    assertions: tuple[str, ...]

    def __post_init__(self) -> None:
        require(
            _PROTOCOL_RE.fullmatch(self.profile) is not None,
            "invalid-conformance",
            "Conformance profiles use lowercase protocol labels.",
        )
        require(
            bool(self.fixtures) and bool(self.assertions),
            "invalid-conformance",
            "Conformance requires fixtures and assertions.",
        )


@dataclass(frozen=True)
class AdapterDeclaration:
    adapter_id: str
    fingerprint: ProtocolFingerprint
    capabilities: tuple[CapabilityRequirement, ...]
    private_access_modes: tuple[PrivateAccessMode, ...]
    learning_bundle: LearningBundle
    conformance: ConformanceContract
    authority_model: str

    def __post_init__(self) -> None:
        require(
            _ADAPTER_ID_RE.fullmatch(self.adapter_id) is not None,
            "invalid-adapter-id",
            "Adapter identifiers use lowercase kebab-case.",
        )
        require(
            bool(self.capabilities),
            "invalid-adapter-declaration",
            "Every adapter must declare capability requirements.",
        )
        require(
            bool(self.private_access_modes),
            "invalid-adapter-declaration",
            "Every adapter must declare private access modes.",
        )
        require(
            bool(self.authority_model.strip()),
            "invalid-adapter-declaration",
            "Every adapter must declare its authority model.",
        )


@runtime_checkable
class DeclaredAdapter(Protocol):
    declaration: AdapterDeclaration


def contract_document(
    protocol: str,
    contract: dict[str, Any],
    *,
    source: str,
) -> tuple[ProtocolFingerprint, LearningBundle]:
    encoded = canonical_json(contract).decode("utf-8")
    fingerprint = ProtocolFingerprint.from_contract(protocol, contract)
    document = LearningDocument.embedded(
        name=f"{protocol}-contract.json",
        media_type="application/json",
        source=source,
        content=encoded,
    )
    return (
        fingerprint,
        LearningBundle(
            schema="hive-hub-learning-bundle/1.0",
            documents=(document,),
        ),
    )
