from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal, TypeVar, cast
from urllib.parse import parse_qsl, urlsplit

from .canonical import address_digest, canonical_bytes, content_address, validate_address
from .chant import (
    CHANT_PROTOCOL,
    CHANT_VOCABULARY_SHA256,
    derive_chant,
    normalize_chant,
    validate_dial_record_id,
    verify_chant,
)
from .errors import LimitError, ValidationError
from .limits import (
    MAX_ARRAY_ITEMS,
    MAX_ARTIFACT_BYTES,
    MAX_LEARNING_BUNDLE_BYTES,
    MAX_SHORT_STRING_BYTES,
)

SCHEMA_VERSION = 1
ADAPTER_INTERFACE_VERSION = "hive-hub-adapter/1"
Visibility = Literal["local", "public", "private"]
PrincipalKind = Literal["human", "ai"]
AccessMode = Literal["acl-only", "acl+qr"]
JsonObject = dict[str, Any]
ContractT = TypeVar("ContractT")

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_MEDIA_TYPE_RE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:;[A-Za-z0-9!#$&^_.+\-= ]+)?$"
)
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_QR_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SENSITIVE_NAME_RE = re.compile(
    r"(?:^|[-_.])"
    r"(access[-_]?key|api[-_]?key|authorization|credential|fragment|password|"
    r"private[-_]?key|qr|secret|sig|signature|token)"
    r"(?:$|[-_.])",
    re.IGNORECASE,
)
_QR_DOMAIN = b"hive-hub/private-access/acl+qr/v1\x00"


def _object(value: Any, *, field: str = "document") -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{field} must be a JSON object")
    return cast(JsonObject, value)


def _closed(
    value: Any,
    *,
    required: set[str],
    field: str,
    optional: set[str] | None = None,
) -> JsonObject:
    obj = _object(value, field=field)
    permitted = required | (optional or set())
    extra = set(obj) - permitted
    missing = required - set(obj)
    if extra:
        raise ValidationError(f"{field} has unknown fields: {', '.join(sorted(extra))}")
    if missing:
        raise ValidationError(f"{field} is missing fields: {', '.join(sorted(missing))}")
    return obj


def _fixed_header(
    value: Any,
    kind: str,
    fields: set[str],
    *,
    field: str | None = None,
) -> JsonObject:
    obj = _closed(
        value,
        required={"kind", "schema_version"} | fields,
        field=field or kind,
    )
    if obj["kind"] != kind:
        raise ValidationError(f"kind must be {kind}")
    if obj["schema_version"] != SCHEMA_VERSION:
        raise ValidationError(f"{kind} schema_version must be {SCHEMA_VERSION}")
    return obj


def _string(
    value: Any,
    *,
    field: str,
    minimum: int = 1,
    maximum_bytes: int = MAX_SHORT_STRING_BYTES,
    allow_multiline: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    if len(value) < minimum:
        raise ValidationError(f"{field} must not be empty")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{field} must contain valid Unicode") from exc
    if len(encoded) > maximum_bytes:
        raise LimitError(f"{field} exceeds the configured byte limit")
    allowed_controls = {"\t", "\n", "\r"} if allow_multiline else set()
    if any(ord(character) < 0x20 and character not in allowed_controls for character in value):
        raise ValidationError(f"{field} must not contain control characters")
    return value


def _nullable_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field=field)


def _slug(value: Any, *, field: str) -> str:
    text = _string(value, field=field, maximum_bytes=128)
    if _SLUG_RE.fullmatch(text) is None:
        raise ValidationError(f"{field} must be a lowercase slug")
    return text


def _media_type(value: Any, *, field: str) -> str:
    text = _string(value, field=field, maximum_bytes=256)
    if _MEDIA_TYPE_RE.fullmatch(text) is None:
        raise ValidationError(f"{field} must be a media type")
    return text


def _literal(value: Any, choices: set[str], *, field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(choices))}")
    return value


def _boolean(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a boolean")
    return value


def _array(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be an array")
    if len(value) > MAX_ARRAY_ITEMS:
        raise LimitError(f"{field} exceeds the configured item limit")
    return value


def _sorted_unique_strings(
    value: Any,
    *,
    field: str,
    normalize: bool = False,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    raw = _array(value, field=field)
    values = tuple(
        normalize_chant(item) if normalize else _string(item, field=f"{field} item") for item in raw
    )
    if not allow_empty and not values:
        raise ValidationError(f"{field} must contain at least one item")
    if values != tuple(sorted(set(values))):
        raise ValidationError(f"{field} must be sorted and contain no duplicates")
    return values


def _canonical_time(value: Any, *, field: str) -> str:
    text = _string(value, field=field, maximum_bytes=32)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an RFC 3339 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"{field} must use UTC")
    canonical = (
        parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    if text != canonical:
        raise ValidationError(f"{field} must use canonical second-precision UTC form")
    return text


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_bare_qr_factor(text: str) -> bool:
    if _QR_RE.fullmatch(text.strip()) is None:
        return False
    try:
        normalize_chant(text)
    except ValidationError:
        return True
    return False


def normalize_record_chant(value: Any) -> str:
    text = _string(value, field="chant", maximum_bytes=512)
    if _is_bare_qr_factor(text):
        raise ValidationError("a QR factor cannot be used as a chant")
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    if not normalized:
        raise ValidationError("chant must not be empty")
    if len(normalized.encode("utf-8")) > 512:
        raise LimitError("chant exceeds the configured byte limit")
    return normalized


def validate_locator(value: Any, *, field: str = "locator") -> str:
    locator = _string(value, field=field, maximum_bytes=4096)
    if "#" in locator:
        raise ValidationError(f"{field} must not contain a URL fragment")
    if _URI_SCHEME_RE.match(locator) is None:
        raise ValidationError(f"{field} must be an absolute URI")
    try:
        parsed = urlsplit(locator)
        username = parsed.username
        password = parsed.password
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValidationError(f"{field} must be a valid absolute URI") from exc
    if username is not None or password is not None:
        raise ValidationError(f"{field} must not contain credentials")
    if parsed.scheme in {"http", "https"} and not hostname:
        raise ValidationError(f"{field} must have a host")
    for name, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if _SENSITIVE_NAME_RE.search(name):
            raise ValidationError(f"{field} must not contain credential query parameters")
    return locator


def validate_dial_query(value: Any) -> str:
    query = _string(value, field="dial query", maximum_bytes=4096)
    if "#" in query:
        raise ValidationError("dial query must not contain a URL fragment")
    if _is_bare_qr_factor(query):
        raise ValidationError("dial query must not be a bare QR factor")
    if _URI_SCHEME_RE.match(query) is not None:
        validate_locator(query, field="dial query")
    return query


def _artifact_name(value: Any) -> str:
    name = _string(value, field="artifact name", maximum_bytes=512)
    if name.startswith("/") or "\\" in name:
        raise ValidationError("artifact name must be a safe relative POSIX path")
    parts = name.split("/")
    if len(parts) > 8 or any(part in ("", ".", "..") for part in parts):
        raise ValidationError("artifact name must be a safe relative POSIX path")
    return name


def _check_body_id(identifier: Any, body: JsonObject, *, field: str) -> str:
    actual = validate_address(identifier, field=field)
    expected = content_address(body)
    if not hmac.compare_digest(actual, expected):
        raise ValidationError(f"{field} does not match the canonical identity body")
    return actual


@dataclass(frozen=True, slots=True)
class ConformanceRequirement:
    requirement_id: str
    description: str

    @classmethod
    def from_dict(cls, value: Any) -> ConformanceRequirement:
        obj = _closed(
            value,
            required={"id", "description"},
            field="conformance requirement",
        )
        return cls(
            requirement_id=_slug(obj["id"], field="conformance requirement id"),
            description=_string(obj["description"], field="conformance requirement description"),
        )

    def to_dict(self) -> JsonObject:
        return {"id": self.requirement_id, "description": self.description}


@dataclass(frozen=True, slots=True)
class ConformanceContract:
    kind: ClassVar[str] = "conformance-contract"
    version: str
    requirements: tuple[ConformanceRequirement, ...]

    @classmethod
    def create(
        cls,
        *,
        version: str,
        requirements: list[ConformanceRequirement] | tuple[ConformanceRequirement, ...],
    ) -> ConformanceContract:
        ordered = tuple(sorted(requirements, key=lambda item: item.requirement_id))
        contract = cls(_string(version, field="conformance version"), ordered)
        return cls.from_dict(contract.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> ConformanceContract:
        obj = _fixed_header(value, cls.kind, {"version", "requirements"})
        requirements = tuple(
            ConformanceRequirement.from_dict(item)
            for item in _array(obj["requirements"], field="conformance requirements")
        )
        identifiers = tuple(item.requirement_id for item in requirements)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValidationError("conformance requirements must be sorted by unique id")
        return cls(
            version=_string(obj["version"], field="conformance version"),
            requirements=requirements,
        )

    @property
    def address(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "version": self.version,
            "requirements": [item.to_dict() for item in self.requirements],
        }


@dataclass(frozen=True, slots=True)
class ProtocolDeclaration:
    kind: ClassVar[str] = "protocol-declaration"
    name: str
    protocol_version: str
    adapter_api_version: str
    media_type: str
    capabilities: tuple[str, ...]
    conformance_address: str

    @classmethod
    def create(
        cls,
        *,
        name: str,
        protocol_version: str,
        media_type: str,
        capabilities: list[str] | tuple[str, ...],
        conformance_address: str,
        adapter_api_version: str = ADAPTER_INTERFACE_VERSION,
    ) -> ProtocolDeclaration:
        declaration = cls(
            name=_string(name, field="protocol name"),
            protocol_version=_string(protocol_version, field="protocol version"),
            adapter_api_version=_string(adapter_api_version, field="adapter API version"),
            media_type=_media_type(media_type, field="protocol media type"),
            capabilities=tuple(sorted(set(capabilities))),
            conformance_address=validate_address(conformance_address, field="conformance address"),
        )
        return cls.from_dict(declaration.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> ProtocolDeclaration:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "name",
                "protocol_version",
                "adapter_api_version",
                "media_type",
                "capabilities",
                "conformance_address",
            },
        )
        capabilities = _sorted_unique_strings(
            obj["capabilities"],
            field="protocol capabilities",
            allow_empty=False,
        )
        for capability in capabilities:
            _slug(capability, field="protocol capability")
        return cls(
            name=_string(obj["name"], field="protocol name"),
            protocol_version=_string(obj["protocol_version"], field="protocol version"),
            adapter_api_version=_string(obj["adapter_api_version"], field="adapter API version"),
            media_type=_media_type(obj["media_type"], field="protocol media type"),
            capabilities=capabilities,
            conformance_address=validate_address(
                obj["conformance_address"], field="conformance address"
            ),
        )

    @property
    def fingerprint(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "protocol_version": self.protocol_version,
            "adapter_api_version": self.adapter_api_version,
            "media_type": self.media_type,
            "capabilities": list(self.capabilities),
            "conformance_address": self.conformance_address,
        }


@dataclass(frozen=True, slots=True)
class ProtocolFingerprint:
    kind: ClassVar[str] = "protocol-fingerprint"
    algorithm: Literal["sha256"]
    value: str

    @classmethod
    def from_declaration(cls, declaration: ProtocolDeclaration) -> ProtocolFingerprint:
        return cls(algorithm="sha256", value=declaration.fingerprint)

    @classmethod
    def from_dict(cls, value: Any) -> ProtocolFingerprint:
        obj = _fixed_header(value, cls.kind, {"algorithm", "value"})
        if obj["algorithm"] != "sha256":
            raise ValidationError("protocol fingerprint algorithm must be sha256")
        return cls(
            algorithm="sha256",
            value=validate_address(obj["value"], field="protocol fingerprint"),
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "algorithm": self.algorithm,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class LearningArtifact:
    name: str
    media_type: str
    encoding: Literal["utf-8"]
    content: str
    content_address: str

    @classmethod
    def create(cls, *, name: str, media_type: str, content: str) -> LearningArtifact:
        content_text = _string(
            content,
            field="learning artifact content",
            minimum=0,
            maximum_bytes=MAX_ARTIFACT_BYTES,
            allow_multiline=True,
        )
        encoded = content_text.encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise LimitError("learning artifact exceeds the configured byte limit")
        artifact = cls(
            name=_artifact_name(name),
            media_type=_media_type(media_type, field="artifact media type"),
            encoding="utf-8",
            content=content_text,
            content_address=content_address(encoded, raw=True),
        )
        return cls.from_dict(artifact.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> LearningArtifact:
        obj = _closed(
            value,
            required={"name", "media_type", "encoding", "content", "content_address"},
            field="learning artifact",
        )
        if obj["encoding"] != "utf-8":
            raise ValidationError("learning artifact encoding must be utf-8")
        content = _string(
            obj["content"],
            field="learning artifact content",
            minimum=0,
            maximum_bytes=MAX_ARTIFACT_BYTES,
            allow_multiline=True,
        )
        expected = content_address(content.encode("utf-8"), raw=True)
        actual = validate_address(obj["content_address"], field="artifact content address")
        if not hmac.compare_digest(expected, actual):
            raise ValidationError("artifact content address does not match its bytes")
        return cls(
            name=_artifact_name(obj["name"]),
            media_type=_media_type(obj["media_type"], field="artifact media type"),
            encoding="utf-8",
            content=content,
            content_address=actual,
        )

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "media_type": self.media_type,
            "encoding": self.encoding,
            "content": self.content,
            "content_address": self.content_address,
        }


@dataclass(frozen=True, slots=True)
class LearningBundle:
    kind: ClassVar[str] = "learning-bundle"
    protocol_fingerprint: str
    bundle_version: str
    summary: str
    conformance_contract: ConformanceContract
    artifacts: tuple[LearningArtifact, ...]

    @classmethod
    def create(
        cls,
        *,
        protocol_fingerprint: str,
        bundle_version: str,
        summary: str,
        conformance_contract: ConformanceContract,
        artifacts: list[LearningArtifact] | tuple[LearningArtifact, ...],
    ) -> LearningBundle:
        ordered = tuple(sorted(artifacts, key=lambda item: item.name))
        bundle = cls(
            protocol_fingerprint=validate_address(
                protocol_fingerprint, field="protocol fingerprint"
            ),
            bundle_version=_string(bundle_version, field="bundle version"),
            summary=_string(summary, field="learning bundle summary"),
            conformance_contract=conformance_contract,
            artifacts=ordered,
        )
        return cls.from_dict(bundle.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> LearningBundle:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "protocol_fingerprint",
                "bundle_version",
                "summary",
                "conformance_contract",
                "artifacts",
            },
        )
        artifacts = tuple(
            LearningArtifact.from_dict(item)
            for item in _array(obj["artifacts"], field="learning artifacts")
        )
        names = tuple(item.name for item in artifacts)
        if names != tuple(sorted(set(names))):
            raise ValidationError("learning artifacts must be sorted by unique name")
        bundle = cls(
            protocol_fingerprint=validate_address(
                obj["protocol_fingerprint"], field="protocol fingerprint"
            ),
            bundle_version=_string(obj["bundle_version"], field="bundle version"),
            summary=_string(obj["summary"], field="learning bundle summary"),
            conformance_contract=ConformanceContract.from_dict(obj["conformance_contract"]),
            artifacts=artifacts,
        )
        if len(canonical_bytes(bundle.to_dict())) > MAX_LEARNING_BUNDLE_BYTES:
            raise LimitError("learning bundle exceeds the configured byte limit")
        return bundle

    @property
    def address(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "protocol_fingerprint": self.protocol_fingerprint,
            "bundle_version": self.bundle_version,
            "summary": self.summary,
            "conformance_contract": self.conformance_contract.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    kind: ClassVar[str] = "adapter-registration"
    protocol_fingerprint: str
    name: str
    adapter_version: str
    interface_version: str
    locator: str
    conformance_address: str
    operations: tuple[str, ...]
    effect_kinds: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        protocol_fingerprint: str,
        name: str,
        adapter_version: str,
        locator: str,
        conformance_address: str,
        operations: list[str] | tuple[str, ...],
        effect_kinds: list[str] | tuple[str, ...] = (),
        interface_version: str = ADAPTER_INTERFACE_VERSION,
    ) -> AdapterRegistration:
        registration = cls(
            protocol_fingerprint=validate_address(
                protocol_fingerprint, field="protocol fingerprint"
            ),
            name=_string(name, field="adapter name"),
            adapter_version=_string(adapter_version, field="adapter version"),
            interface_version=_string(interface_version, field="adapter interface version"),
            locator=validate_locator(locator, field="adapter locator"),
            conformance_address=validate_address(
                conformance_address, field="adapter conformance address"
            ),
            operations=tuple(sorted(set(operations))),
            effect_kinds=tuple(sorted(set(effect_kinds))),
        )
        return cls.from_dict(registration.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> AdapterRegistration:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "protocol_fingerprint",
                "name",
                "adapter_version",
                "interface_version",
                "locator",
                "conformance_address",
                "operations",
                "effect_kinds",
            },
        )
        operations = _sorted_unique_strings(
            obj["operations"], field="adapter operations", allow_empty=False
        )
        effect_kinds = _sorted_unique_strings(obj["effect_kinds"], field="adapter effect kinds")
        for operation in operations:
            _slug(operation, field="adapter operation")
        allowed_effects = {"authenticate", "clone", "execute", "fetch", "other", "write"}
        for effect_kind in effect_kinds:
            _literal(effect_kind, allowed_effects, field="adapter effect kind")
        return cls(
            protocol_fingerprint=validate_address(
                obj["protocol_fingerprint"], field="protocol fingerprint"
            ),
            name=_string(obj["name"], field="adapter name"),
            adapter_version=_string(obj["adapter_version"], field="adapter version"),
            interface_version=_string(obj["interface_version"], field="adapter interface version"),
            locator=validate_locator(obj["locator"], field="adapter locator"),
            conformance_address=validate_address(
                obj["conformance_address"], field="adapter conformance address"
            ),
            operations=operations,
            effect_kinds=effect_kinds,
        )

    @property
    def address(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "protocol_fingerprint": self.protocol_fingerprint,
            "name": self.name,
            "adapter_version": self.adapter_version,
            "interface_version": self.interface_version,
            "locator": self.locator,
            "conformance_address": self.conformance_address,
            "operations": list(self.operations),
            "effect_kinds": list(self.effect_kinds),
        }


@dataclass(frozen=True, slots=True)
class AdapterEffect:
    effect_id: str
    kind: str
    description: str
    locator: str | None
    requires_approval: Literal[True]

    @classmethod
    def create(
        cls,
        *,
        effect_id: str,
        kind: str,
        description: str,
        locator: str | None = None,
    ) -> AdapterEffect:
        effect = cls(
            effect_id=_slug(effect_id, field="adapter effect id"),
            kind=_literal(
                kind,
                {"authenticate", "clone", "execute", "fetch", "other", "write"},
                field="adapter effect kind",
            ),
            description=_string(description, field="adapter effect description"),
            locator=None if locator is None else validate_locator(locator),
            requires_approval=True,
        )
        return cls.from_dict(effect.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> AdapterEffect:
        obj = _closed(
            value,
            required={"effect_id", "kind", "description", "locator", "requires_approval"},
            field="adapter effect",
        )
        if obj["requires_approval"] is not True:
            raise ValidationError("adapter effects must require explicit approval")
        effect_id = _slug(obj["effect_id"], field="adapter effect id")
        if _SENSITIVE_NAME_RE.search(effect_id):
            raise ValidationError("adapter effect ids must not name secret material")
        locator = _nullable_string(obj["locator"], field="adapter effect locator")
        return cls(
            effect_id=effect_id,
            kind=_literal(
                obj["kind"],
                {"authenticate", "clone", "execute", "fetch", "other", "write"},
                field="adapter effect kind",
            ),
            description=_string(obj["description"], field="adapter effect description"),
            locator=None if locator is None else validate_locator(locator),
            requires_approval=True,
        )

    def to_dict(self) -> JsonObject:
        return {
            "effect_id": self.effect_id,
            "kind": self.kind,
            "description": self.description,
            "locator": self.locator,
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True, slots=True)
class AdapterPlan:
    kind: ClassVar[str] = "adapter-plan"
    adapter_registration_address: str
    record_id: str
    effects: tuple[AdapterEffect, ...]

    @classmethod
    def create(
        cls,
        *,
        adapter_registration_address: str,
        record_id: str,
        effects: list[AdapterEffect] | tuple[AdapterEffect, ...],
    ) -> AdapterPlan:
        ordered = tuple(sorted(effects, key=lambda item: item.effect_id))
        plan = cls(
            adapter_registration_address=validate_address(
                adapter_registration_address, field="adapter registration address"
            ),
            record_id=validate_address(record_id, field="record id"),
            effects=ordered,
        )
        return cls.from_dict(plan.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> AdapterPlan:
        obj = _fixed_header(
            value,
            cls.kind,
            {"adapter_registration_address", "record_id", "effects"},
        )
        effects = tuple(
            AdapterEffect.from_dict(item)
            for item in _array(obj["effects"], field="adapter effects")
        )
        identifiers = tuple(item.effect_id for item in effects)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValidationError("adapter effects must be sorted by unique effect id")
        return cls(
            adapter_registration_address=validate_address(
                obj["adapter_registration_address"], field="adapter registration address"
            ),
            record_id=validate_address(obj["record_id"], field="record id"),
            effects=effects,
        )

    @property
    def address(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "adapter_registration_address": self.adapter_registration_address,
            "record_id": self.record_id,
            "effects": [effect.to_dict() for effect in self.effects],
        }


@dataclass(frozen=True, slots=True)
class AdapterRegistrationReceipt:
    kind: ClassVar[str] = "adapter-registration-receipt"
    receipt_id: str
    registration_address: str
    protocol_fingerprint: str
    scope: Visibility
    status: Literal["registered"]
    registered_at: str

    @staticmethod
    def _body(
        *,
        registration_address: str,
        protocol_fingerprint: str,
        scope: str,
        registered_at: str,
    ) -> JsonObject:
        return {
            "kind": "adapter-registration-receipt-body",
            "schema_version": SCHEMA_VERSION,
            "registration_address": registration_address,
            "protocol_fingerprint": protocol_fingerprint,
            "scope": scope,
            "status": "registered",
            "registered_at": registered_at,
        }

    @classmethod
    def create(
        cls,
        *,
        registration: AdapterRegistration,
        scope: Visibility = "local",
        registered_at: str | None = None,
    ) -> AdapterRegistrationReceipt:
        timestamp = registered_at or utc_now()
        body = cls._body(
            registration_address=registration.address,
            protocol_fingerprint=registration.protocol_fingerprint,
            scope=scope,
            registered_at=timestamp,
        )
        receipt = cls(
            receipt_id=content_address(body),
            registration_address=registration.address,
            protocol_fingerprint=registration.protocol_fingerprint,
            scope=scope,
            status="registered",
            registered_at=timestamp,
        )
        return cls.from_dict(receipt.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> AdapterRegistrationReceipt:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "receipt_id",
                "registration_address",
                "protocol_fingerprint",
                "scope",
                "status",
                "registered_at",
            },
        )
        registration_address = validate_address(
            obj["registration_address"], field="adapter registration address"
        )
        protocol_fingerprint = validate_address(
            obj["protocol_fingerprint"], field="protocol fingerprint"
        )
        scope = cast(
            Visibility,
            _literal(obj["scope"], {"local", "public", "private"}, field="receipt scope"),
        )
        if obj["status"] != "registered":
            raise ValidationError("adapter receipt status must be registered")
        registered_at = _canonical_time(obj["registered_at"], field="registered_at")
        body = cls._body(
            registration_address=registration_address,
            protocol_fingerprint=protocol_fingerprint,
            scope=scope,
            registered_at=registered_at,
        )
        return cls(
            receipt_id=_check_body_id(obj["receipt_id"], body, field="receipt id"),
            registration_address=registration_address,
            protocol_fingerprint=protocol_fingerprint,
            scope=scope,
            status="registered",
            registered_at=registered_at,
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "receipt_id": self.receipt_id,
            "registration_address": self.registration_address,
            "protocol_fingerprint": self.protocol_fingerprint,
            "scope": self.scope,
            "status": self.status,
            "registered_at": self.registered_at,
        }


@dataclass(frozen=True, slots=True)
class ChantLocator:
    kind: ClassVar[str] = "chant-locator"
    dial_record_id: str
    chant: str
    protocol: str = CHANT_PROTOCOL
    vocabulary_sha256: str = CHANT_VOCABULARY_SHA256
    candidate_locator_only: bool = True
    full_dial_id_verification_required: bool = True

    @classmethod
    def create(cls, dial_record_id: str) -> ChantLocator:
        canonical_id = validate_dial_record_id(dial_record_id)
        return cls(dial_record_id=canonical_id, chant=derive_chant(canonical_id))

    @classmethod
    def from_dict(cls, value: Any) -> ChantLocator:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "dial_record_id",
                "chant",
                "protocol",
                "vocabulary_sha256",
                "candidate_locator_only",
                "full_dial_id_verification_required",
            },
        )
        dial_record_id = validate_dial_record_id(obj["dial_record_id"])
        chant = verify_chant(dial_record_id, obj["chant"])
        if obj["protocol"] != CHANT_PROTOCOL:
            raise ValidationError(f"chant protocol must be {CHANT_PROTOCOL}")
        if obj["vocabulary_sha256"] != CHANT_VOCABULARY_SHA256:
            raise ValidationError("chant vocabulary hash does not match the frozen vocabulary")
        if not _boolean(obj["candidate_locator_only"], field="candidate locator only"):
            raise ValidationError("a chant must remain a candidate locator only")
        if not _boolean(
            obj["full_dial_id_verification_required"],
            field="full dial id verification required",
        ):
            raise ValidationError("the full Dial Record ID must be verified")
        return cls(dial_record_id=dial_record_id, chant=chant)

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "dial_record_id": self.dial_record_id,
            "chant": self.chant,
            "protocol": self.protocol,
            "vocabulary_sha256": self.vocabulary_sha256,
            "candidate_locator_only": self.candidate_locator_only,
            "full_dial_id_verification_required": self.full_dial_id_verification_required,
        }


@dataclass(frozen=True, slots=True)
class DialRecord:
    kind: ClassVar[str] = "dial-record"
    id: str
    name: str
    description: str
    visibility: Visibility
    protocol_fingerprint: str
    learning_bundle_address: str
    adapter_registration_address: str
    urls: tuple[str, ...]
    chants: tuple[str, ...]

    @property
    def dial_id(self) -> str:
        return "dial:sha256:" + address_digest(self.id)

    @property
    def index_chants(self) -> tuple[str, ...]:
        return tuple(sorted({*self.chants, derive_chant(self.dial_id)}))

    @staticmethod
    def _body(
        *,
        name: str,
        description: str,
        visibility: str,
        protocol_fingerprint: str,
        learning_bundle_address: str,
        adapter_registration_address: str,
        urls: tuple[str, ...],
        chants: tuple[str, ...],
    ) -> JsonObject:
        return {
            "kind": "dial-record-body",
            "schema_version": SCHEMA_VERSION,
            "name": name,
            "description": description,
            "visibility": visibility,
            "protocol_fingerprint": protocol_fingerprint,
            "learning_bundle_address": learning_bundle_address,
            "adapter_registration_address": adapter_registration_address,
            "urls": list(urls),
            "chants": list(chants),
        }

    @classmethod
    def create(
        cls,
        *,
        name: str,
        description: str,
        visibility: Visibility,
        protocol_fingerprint: str,
        learning_bundle_address: str,
        adapter_registration_address: str,
        urls: list[str] | tuple[str, ...] = (),
        chants: list[str] | tuple[str, ...] = (),
    ) -> DialRecord:
        normalized_urls = tuple(
            sorted(set(validate_locator(item, field="dial URL") for item in urls))
        )
        normalized_chants = tuple(
            sorted(set(normalize_record_chant(item) for item in chants))
        )
        if not normalized_urls and not normalized_chants:
            raise ValidationError("dial record requires at least one URL or chant")
        body = cls._body(
            name=_string(name, field="record name"),
            description=_string(description, field="record description", minimum=0),
            visibility=visibility,
            protocol_fingerprint=validate_address(
                protocol_fingerprint, field="protocol fingerprint"
            ),
            learning_bundle_address=validate_address(
                learning_bundle_address, field="learning bundle address"
            ),
            adapter_registration_address=validate_address(
                adapter_registration_address, field="adapter registration address"
            ),
            urls=normalized_urls,
            chants=normalized_chants,
        )
        record = cls(
            id=content_address(body),
            name=cast(str, body["name"]),
            description=cast(str, body["description"]),
            visibility=visibility,
            protocol_fingerprint=cast(str, body["protocol_fingerprint"]),
            learning_bundle_address=cast(str, body["learning_bundle_address"]),
            adapter_registration_address=cast(str, body["adapter_registration_address"]),
            urls=normalized_urls,
            chants=normalized_chants,
        )
        return cls.from_dict(record.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> DialRecord:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "id",
                "name",
                "description",
                "visibility",
                "protocol_fingerprint",
                "learning_bundle_address",
                "adapter_registration_address",
                "urls",
                "chants",
            },
        )
        visibility = cast(
            Visibility,
            _literal(
                obj["visibility"],
                {"local", "public", "private"},
                field="record visibility",
            ),
        )
        urls = _sorted_unique_strings(obj["urls"], field="dial URLs")
        urls = tuple(validate_locator(item, field="dial URL") for item in urls)
        chants = tuple(
            normalize_record_chant(item)
            for item in _sorted_unique_strings(obj["chants"], field="chants")
        )
        if not urls and not chants:
            raise ValidationError("dial record requires at least one URL or chant")
        name = _string(obj["name"], field="record name")
        description = _string(obj["description"], field="record description", minimum=0)
        protocol_fingerprint = validate_address(
            obj["protocol_fingerprint"], field="protocol fingerprint"
        )
        learning_bundle_address = validate_address(
            obj["learning_bundle_address"], field="learning bundle address"
        )
        adapter_registration_address = validate_address(
            obj["adapter_registration_address"], field="adapter registration address"
        )
        body = cls._body(
            name=name,
            description=description,
            visibility=visibility,
            protocol_fingerprint=protocol_fingerprint,
            learning_bundle_address=learning_bundle_address,
            adapter_registration_address=adapter_registration_address,
            urls=urls,
            chants=chants,
        )
        return cls(
            id=_check_body_id(obj["id"], body, field="record id"),
            name=name,
            description=description,
            visibility=visibility,
            protocol_fingerprint=protocol_fingerprint,
            learning_bundle_address=learning_bundle_address,
            adapter_registration_address=adapter_registration_address,
            urls=urls,
            chants=chants,
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "visibility": self.visibility,
            "protocol_fingerprint": self.protocol_fingerprint,
            "learning_bundle_address": self.learning_bundle_address,
            "adapter_registration_address": self.adapter_registration_address,
            "urls": list(self.urls),
            "chants": list(self.chants),
        }

def validate_record_contracts(
    record: DialRecord,
    declaration: ProtocolDeclaration,
    bundle: LearningBundle,
    adapter: AdapterRegistration,
) -> None:
    if (
        record.protocol_fingerprint != declaration.fingerprint
        or record.learning_bundle_address != bundle.address
        or record.adapter_registration_address != adapter.address
    ):
        raise ValidationError("record contract content address mismatch")
    if bundle.protocol_fingerprint != declaration.fingerprint:
        raise ValidationError("record learning bundle belongs to another protocol")
    if adapter.protocol_fingerprint != declaration.fingerprint:
        raise ValidationError("record adapter belongs to another protocol")
    if bundle.conformance_contract.address != declaration.conformance_address:
        raise ValidationError("record learning bundle conformance mismatch")
    if adapter.conformance_address != declaration.conformance_address:
        raise ValidationError("record adapter conformance mismatch")
    if adapter.interface_version != declaration.adapter_api_version:
        raise ValidationError("adapter interface version does not match the protocol")


def generate_qr_fragment() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def decode_qr_fragment(fragment: Any) -> bytes:
    text = _string(fragment, field="QR fragment", maximum_bytes=43)
    if _QR_RE.fullmatch(text) is None:
        raise ValidationError("QR fragment must be canonical 256-bit base64url without padding")
    try:
        decoded = base64.urlsafe_b64decode(text + "=")
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("QR fragment is not valid base64url") from exc
    if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != text:
        raise ValidationError("QR fragment must encode exactly 256 bits")
    return decoded


def qr_commitment(*, record_id: str, scope: str, epoch: str, fragment: str) -> str:
    record = validate_address(record_id, field="private policy record id")
    scope_text = _string(scope, field="private policy scope", maximum_bytes=512)
    epoch_text = _string(epoch, field="private policy epoch", maximum_bytes=256)
    digest = hashlib.sha256()
    digest.update(_QR_DOMAIN)
    for item in (record.encode("utf-8"), scope_text.encode("utf-8"), epoch_text.encode("utf-8")):
        digest.update(len(item).to_bytes(4, "big"))
        digest.update(item)
    digest.update(decode_qr_fragment(fragment))
    return "urn:hivehub:sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class PrivateAccessPolicy:
    kind: ClassVar[str] = "private-access-policy"
    record_id: str
    mode: AccessMode
    scope: str
    epoch: str
    qr_commitment: str | None

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        scope: str | None = None,
        epoch: str = "1",
        mode: AccessMode = "acl-only",
        qr_fragment: str | None = None,
    ) -> PrivateAccessPolicy:
        record = validate_address(record_id, field="private policy record id")
        scope_text = scope or record
        commitment: str | None = None
        if mode == "acl+qr":
            if qr_fragment is None:
                raise ValidationError("acl+qr requires a QR fragment")
            commitment = qr_commitment(
                record_id=record,
                scope=scope_text,
                epoch=epoch,
                fragment=qr_fragment,
            )
        elif qr_fragment is not None:
            raise ValidationError("acl-only policy must not receive a QR fragment")
        policy = cls(
            record_id=record,
            mode=mode,
            scope=_string(scope_text, field="private policy scope", maximum_bytes=512),
            epoch=_string(epoch, field="private policy epoch", maximum_bytes=256),
            qr_commitment=commitment,
        )
        return cls.from_dict(policy.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> PrivateAccessPolicy:
        obj = _fixed_header(
            value,
            cls.kind,
            {"record_id", "mode", "scope", "epoch", "qr_commitment"},
        )
        mode = cast(
            AccessMode,
            _literal(obj["mode"], {"acl-only", "acl+qr"}, field="private access mode"),
        )
        commitment_value = obj["qr_commitment"]
        if mode == "acl-only":
            if commitment_value is not None:
                raise ValidationError("acl-only policy must have a null QR commitment")
            commitment = None
        else:
            commitment = validate_address(commitment_value, field="private policy QR commitment")
        return cls(
            record_id=validate_address(obj["record_id"], field="private policy record id"),
            mode=mode,
            scope=_string(obj["scope"], field="private policy scope", maximum_bytes=512),
            epoch=_string(obj["epoch"], field="private policy epoch", maximum_bytes=256),
            qr_commitment=commitment,
        )

    def permits(self, *, acl_authorized: bool, qr_fragment: str | None = None) -> bool:
        _boolean(acl_authorized, field="ACL authorization")
        if not acl_authorized:
            return False
        if self.mode == "acl-only":
            return True
        if qr_fragment is None or self.qr_commitment is None:
            return False
        try:
            candidate = qr_commitment(
                record_id=self.record_id,
                scope=self.scope,
                epoch=self.epoch,
                fragment=qr_fragment,
            )
        except ValidationError:
            return False
        return hmac.compare_digest(candidate, self.qr_commitment)

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "record_id": self.record_id,
            "mode": self.mode,
            "scope": self.scope,
            "epoch": self.epoch,
            "qr_commitment": self.qr_commitment,
        }


@dataclass(frozen=True, slots=True)
class Principal:
    kind: PrincipalKind
    id: str

    @classmethod
    def create(cls, *, kind: PrincipalKind, identifier: str) -> Principal:
        principal = cls(
            kind=cast(
                PrincipalKind,
                _literal(kind, {"human", "ai"}, field="principal kind"),
            ),
            id=_string(identifier, field="principal id", maximum_bytes=512),
        )
        return cls.from_dict(principal.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> Principal:
        obj = _closed(value, required={"kind", "id"}, field="principal")
        return cls(
            kind=cast(
                PrincipalKind,
                _literal(obj["kind"], {"human", "ai"}, field="principal kind"),
            ),
            id=_string(obj["id"], field="principal id", maximum_bytes=512),
        )

    def to_dict(self) -> JsonObject:
        return {"kind": self.kind, "id": self.id}


@dataclass(frozen=True, slots=True)
class AIJoinCard:
    kind: ClassVar[str] = "ai-join-card"
    card_id: str
    principal: Principal
    locator: str
    expected_record_id: str | None
    expected_protocol_fingerprint: str | None
    adapter_plan: AdapterPlan | None
    issued_at: str

    @staticmethod
    def _body(
        *,
        principal: Principal,
        locator: str,
        expected_record_id: str | None,
        expected_protocol_fingerprint: str | None,
        adapter_plan: AdapterPlan | None,
        issued_at: str,
    ) -> JsonObject:
        return {
            "kind": "ai-join-card-body",
            "schema_version": SCHEMA_VERSION,
            "principal": principal.to_dict(),
            "locator": locator,
            "expected_record_id": expected_record_id,
            "expected_protocol_fingerprint": expected_protocol_fingerprint,
            "adapter_plan": None if adapter_plan is None else adapter_plan.to_dict(),
            "issued_at": issued_at,
        }

    @classmethod
    def create(
        cls,
        *,
        principal: Principal,
        locator: str,
        expected_record_id: str | None = None,
        expected_protocol_fingerprint: str | None = None,
        adapter_plan: AdapterPlan | None = None,
        issued_at: str | None = None,
    ) -> AIJoinCard:
        query = validate_dial_query(locator)
        timestamp = issued_at or utc_now()
        body = cls._body(
            principal=principal,
            locator=query,
            expected_record_id=(
                None
                if expected_record_id is None
                else validate_address(expected_record_id, field="expected record id")
            ),
            expected_protocol_fingerprint=(
                None
                if expected_protocol_fingerprint is None
                else validate_address(
                    expected_protocol_fingerprint,
                    field="expected protocol fingerprint",
                )
            ),
            adapter_plan=adapter_plan,
            issued_at=timestamp,
        )
        card = cls(
            card_id=content_address(body),
            principal=principal,
            locator=query,
            expected_record_id=cast(str | None, body["expected_record_id"]),
            expected_protocol_fingerprint=cast(str | None, body["expected_protocol_fingerprint"]),
            adapter_plan=adapter_plan,
            issued_at=timestamp,
        )
        return cls.from_dict(card.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> AIJoinCard:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "card_id",
                "principal",
                "locator",
                "expected_record_id",
                "expected_protocol_fingerprint",
                "adapter_plan",
                "issued_at",
            },
        )
        principal = Principal.from_dict(obj["principal"])
        locator = validate_dial_query(obj["locator"])
        expected_record_id = obj["expected_record_id"]
        if expected_record_id is not None:
            expected_record_id = validate_address(expected_record_id, field="expected record id")
        expected_protocol = obj["expected_protocol_fingerprint"]
        if expected_protocol is not None:
            expected_protocol = validate_address(
                expected_protocol, field="expected protocol fingerprint"
            )
        adapter_value = obj["adapter_plan"]
        adapter_plan = None if adapter_value is None else AdapterPlan.from_dict(adapter_value)
        issued_at = _canonical_time(obj["issued_at"], field="join card issued_at")
        body = cls._body(
            principal=principal,
            locator=locator,
            expected_record_id=expected_record_id,
            expected_protocol_fingerprint=expected_protocol,
            adapter_plan=adapter_plan,
            issued_at=issued_at,
        )
        return cls(
            card_id=_check_body_id(obj["card_id"], body, field="join card id"),
            principal=principal,
            locator=locator,
            expected_record_id=cast(str | None, expected_record_id),
            expected_protocol_fingerprint=cast(str | None, expected_protocol),
            adapter_plan=adapter_plan,
            issued_at=issued_at,
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "card_id": self.card_id,
            "principal": self.principal.to_dict(),
            "locator": self.locator,
            "expected_record_id": self.expected_record_id,
            "expected_protocol_fingerprint": self.expected_protocol_fingerprint,
            "adapter_plan": None if self.adapter_plan is None else self.adapter_plan.to_dict(),
            "issued_at": self.issued_at,
        }


@dataclass(frozen=True, slots=True)
class LocalSubscription:
    kind: ClassVar[str] = "local-subscription"
    id: str
    record_id: str
    record_visibility: Visibility
    protocol_fingerprint: str
    learning_bundle_address: str
    adapter_registration_address: str
    locator: str
    principal: Principal
    state: Literal["active"]
    adapter_plan_address: str | None
    adapter_effects_status: Literal["not-required", "not-executed"]
    created_at: str

    @staticmethod
    def _body(
        *,
        record_id: str,
        record_visibility: str,
        protocol_fingerprint: str,
        learning_bundle_address: str,
        adapter_registration_address: str,
        locator: str,
        principal: Principal,
        adapter_plan_address: str | None,
        adapter_effects_status: str,
        created_at: str,
    ) -> JsonObject:
        return {
            "kind": "local-subscription-body",
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "record_visibility": record_visibility,
            "protocol_fingerprint": protocol_fingerprint,
            "learning_bundle_address": learning_bundle_address,
            "adapter_registration_address": adapter_registration_address,
            "locator": locator,
            "principal": principal.to_dict(),
            "state": "active",
            "adapter_plan_address": adapter_plan_address,
            "adapter_effects_status": adapter_effects_status,
            "created_at": created_at,
        }

    @classmethod
    def create(
        cls,
        *,
        record: DialRecord,
        locator: str,
        principal: Principal,
        adapter_plan: AdapterPlan | None = None,
        created_at: str | None = None,
    ) -> LocalSubscription:
        timestamp = created_at or utc_now()
        plan_address = None if adapter_plan is None else adapter_plan.address
        effects_status = (
            "not-required" if adapter_plan is None or not adapter_plan.effects else "not-executed"
        )
        body = cls._body(
            record_id=record.id,
            record_visibility=record.visibility,
            protocol_fingerprint=record.protocol_fingerprint,
            learning_bundle_address=record.learning_bundle_address,
            adapter_registration_address=record.adapter_registration_address,
            locator=validate_dial_query(locator),
            principal=principal,
            adapter_plan_address=plan_address,
            adapter_effects_status=effects_status,
            created_at=timestamp,
        )
        subscription = cls(
            id=content_address(body),
            record_id=record.id,
            record_visibility=record.visibility,
            protocol_fingerprint=record.protocol_fingerprint,
            learning_bundle_address=record.learning_bundle_address,
            adapter_registration_address=record.adapter_registration_address,
            locator=cast(str, body["locator"]),
            principal=principal,
            state="active",
            adapter_plan_address=plan_address,
            adapter_effects_status=cast(Literal["not-required", "not-executed"], effects_status),
            created_at=timestamp,
        )
        return cls.from_dict(subscription.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> LocalSubscription:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "id",
                "record_id",
                "record_visibility",
                "protocol_fingerprint",
                "learning_bundle_address",
                "adapter_registration_address",
                "locator",
                "principal",
                "state",
                "adapter_plan_address",
                "adapter_effects_status",
                "created_at",
            },
        )
        record_id = validate_address(obj["record_id"], field="subscription record id")
        visibility = cast(
            Visibility,
            _literal(
                obj["record_visibility"],
                {"local", "public", "private"},
                field="subscription record visibility",
            ),
        )
        protocol = validate_address(
            obj["protocol_fingerprint"], field="subscription protocol fingerprint"
        )
        bundle = validate_address(
            obj["learning_bundle_address"], field="subscription learning bundle address"
        )
        adapter = validate_address(
            obj["adapter_registration_address"],
            field="subscription adapter registration address",
        )
        locator = validate_dial_query(obj["locator"])
        principal = Principal.from_dict(obj["principal"])
        if obj["state"] != "active":
            raise ValidationError("local subscription state must be active")
        plan_address_value = obj["adapter_plan_address"]
        plan_address = (
            None
            if plan_address_value is None
            else validate_address(
                plan_address_value,
                field="subscription adapter plan address",
            )
        )
        effects_status = cast(
            Literal["not-required", "not-executed"],
            _literal(
                obj["adapter_effects_status"],
                {"not-required", "not-executed"},
                field="adapter effects status",
            ),
        )
        if plan_address is None and effects_status != "not-required":
            raise ValidationError(
                "subscription without an adapter plan cannot have pending effects"
            )
        created_at = _canonical_time(obj["created_at"], field="subscription created_at")
        body = cls._body(
            record_id=record_id,
            record_visibility=visibility,
            protocol_fingerprint=protocol,
            learning_bundle_address=bundle,
            adapter_registration_address=adapter,
            locator=locator,
            principal=principal,
            adapter_plan_address=plan_address,
            adapter_effects_status=effects_status,
            created_at=created_at,
        )
        return cls(
            id=_check_body_id(obj["id"], body, field="subscription id"),
            record_id=record_id,
            record_visibility=visibility,
            protocol_fingerprint=protocol,
            learning_bundle_address=bundle,
            adapter_registration_address=adapter,
            locator=locator,
            principal=principal,
            state="active",
            adapter_plan_address=plan_address,
            adapter_effects_status=effects_status,
            created_at=created_at,
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "record_id": self.record_id,
            "record_visibility": self.record_visibility,
            "protocol_fingerprint": self.protocol_fingerprint,
            "learning_bundle_address": self.learning_bundle_address,
            "adapter_registration_address": self.adapter_registration_address,
            "locator": self.locator,
            "principal": self.principal.to_dict(),
            "state": self.state,
            "adapter_plan_address": self.adapter_plan_address,
            "adapter_effects_status": self.adapter_effects_status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class DialIndexEntry:
    id: str
    name: str
    protocol_fingerprint: str
    learning_bundle_address: str
    adapter_registration_address: str
    urls: tuple[str, ...]
    chants: tuple[str, ...]

    @classmethod
    def from_record(cls, record: DialRecord) -> DialIndexEntry:
        chants = tuple(_array(list(record.index_chants), field="indexed chants"))
        return cls(
            id=record.id,
            name=record.name,
            protocol_fingerprint=record.protocol_fingerprint,
            learning_bundle_address=record.learning_bundle_address,
            adapter_registration_address=record.adapter_registration_address,
            urls=record.urls,
            chants=chants,
        )

    @classmethod
    def from_dict(cls, value: Any) -> DialIndexEntry:
        obj = _closed(
            value,
            required={
                "id",
                "name",
                "protocol_fingerprint",
                "learning_bundle_address",
                "adapter_registration_address",
                "urls",
                "chants",
            },
            field="dial index entry",
        )
        urls = tuple(
            validate_locator(item, field="dial URL")
            for item in _sorted_unique_strings(obj["urls"], field="dial URLs")
        )
        chants = tuple(
            normalize_record_chant(item)
            for item in _sorted_unique_strings(obj["chants"], field="chants")
        )
        record_id = validate_address(obj["id"], field="index record id")
        return cls(
            id=record_id,
            name=_string(obj["name"], field="index record name"),
            protocol_fingerprint=validate_address(
                obj["protocol_fingerprint"], field="protocol fingerprint"
            ),
            learning_bundle_address=validate_address(
                obj["learning_bundle_address"], field="learning bundle address"
            ),
            adapter_registration_address=validate_address(
                obj["adapter_registration_address"], field="adapter registration address"
            ),
            urls=urls,
            chants=chants,
        )

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "name": self.name,
            "protocol_fingerprint": self.protocol_fingerprint,
            "learning_bundle_address": self.learning_bundle_address,
            "adapter_registration_address": self.adapter_registration_address,
            "urls": list(self.urls),
            "chants": list(self.chants),
        }


@dataclass(frozen=True, slots=True)
class CandidateSet:
    candidate: str
    record_ids: tuple[str, ...]

    @classmethod
    def create(cls, *, candidate: str, record_ids: list[str]) -> CandidateSet:
        value = _string(candidate, field="dial candidate", maximum_bytes=4096)
        identifiers = tuple(
            sorted(set(validate_address(item, field="candidate record id") for item in record_ids))
        )
        if not identifiers:
            raise ValidationError("candidate set must contain at least one record id")
        return cls(value, identifiers)

    @classmethod
    def from_dict(cls, value: Any) -> CandidateSet:
        obj = _closed(
            value,
            required={"candidate", "record_ids"},
            field="candidate set",
        )
        identifiers = tuple(
            validate_address(item, field="candidate record id")
            for item in _sorted_unique_strings(
                obj["record_ids"], field="candidate record ids", allow_empty=False
            )
        )
        return cls(
            candidate=_string(obj["candidate"], field="dial candidate", maximum_bytes=4096),
            record_ids=identifiers,
        )

    def to_dict(self) -> JsonObject:
        return {"candidate": self.candidate, "record_ids": list(self.record_ids)}


@dataclass(frozen=True, slots=True)
class DialbookIndex:
    visibility: Literal["public", "private"]
    records: tuple[DialIndexEntry, ...]
    chant_candidates: tuple[CandidateSet, ...]
    url_candidates: tuple[CandidateSet, ...]

    @property
    def kind(self) -> str:
        return f"{self.visibility}-dialbook-index"

    @classmethod
    def create(
        cls,
        *,
        visibility: Literal["public", "private"],
        records: list[DialRecord] | tuple[DialRecord, ...],
    ) -> DialbookIndex:
        if visibility not in {"public", "private"}:
            raise ValidationError("dialbook index visibility must be public or private")
        ordered_records = tuple(sorted(records, key=lambda item: item.id))
        if any(record.visibility != visibility for record in ordered_records):
            raise ValidationError("dialbook index cannot mix visibility scopes")
        chant_map: dict[str, list[str]] = {}
        url_map: dict[str, list[str]] = {}
        for record in ordered_records:
            for chant in record.index_chants:
                chant_map.setdefault(chant, []).append(record.id)
            for url in record.urls:
                url_map.setdefault(url, []).append(record.id)
        index = cls(
            visibility=visibility,
            records=tuple(DialIndexEntry.from_record(record) for record in ordered_records),
            chant_candidates=tuple(
                CandidateSet.create(candidate=key, record_ids=values)
                for key, values in sorted(chant_map.items())
            ),
            url_candidates=tuple(
                CandidateSet.create(candidate=key, record_ids=values)
                for key, values in sorted(url_map.items())
            ),
        )
        return cls.from_dict(index.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> DialbookIndex:
        obj = _object(value)
        kind_value = obj.get("kind")
        if kind_value == "public-dialbook-index":
            visibility: Literal["public", "private"] = "public"
        elif kind_value == "private-dialbook-index":
            visibility = "private"
        else:
            raise ValidationError(
                "dialbook index kind must be public-dialbook-index or private-dialbook-index"
            )
        obj = _fixed_header(
            obj,
            cast(str, kind_value),
            {"visibility", "records", "chant_candidates", "url_candidates"},
        )
        if obj["visibility"] != visibility:
            raise ValidationError("dialbook index visibility does not match its kind")
        records = tuple(
            DialIndexEntry.from_dict(item)
            for item in _array(obj["records"], field="dialbook records")
        )
        ids = tuple(item.id for item in records)
        if ids != tuple(sorted(set(ids))):
            raise ValidationError("dialbook records must be sorted by unique id")
        chants = tuple(
            CandidateSet.from_dict(item)
            for item in _array(obj["chant_candidates"], field="chant candidates")
        )
        urls = tuple(
            CandidateSet.from_dict(item)
            for item in _array(obj["url_candidates"], field="URL candidates")
        )
        if tuple(item.candidate for item in chants) != tuple(
            sorted(set(item.candidate for item in chants))
        ):
            raise ValidationError("chant candidate sets must be sorted and unique")
        if tuple(item.candidate for item in urls) != tuple(
            sorted(set(item.candidate for item in urls))
        ):
            raise ValidationError("URL candidate sets must be sorted and unique")
        known = set(ids)
        if any(
            identifier not in known for group in chants + urls for identifier in group.record_ids
        ):
            raise ValidationError("candidate set refers to a record absent from the index")
        expected_chants: dict[str, list[str]] = {}
        expected_urls: dict[str, list[str]] = {}
        for record in records:
            for chant in record.chants:
                expected_chants.setdefault(chant, []).append(record.id)
            for url in record.urls:
                expected_urls.setdefault(url, []).append(record.id)
        actual_chants = {item.candidate: list(item.record_ids) for item in chants}
        actual_urls = {item.candidate: list(item.record_ids) for item in urls}
        if actual_chants != {
            key: sorted(values) for key, values in sorted(expected_chants.items())
        }:
            raise ValidationError("chant candidate sets do not match indexed records")
        if actual_urls != {key: sorted(values) for key, values in sorted(expected_urls.items())}:
            raise ValidationError("URL candidate sets do not match indexed records")
        return cls(
            visibility=visibility,
            records=records,
            chant_candidates=chants,
            url_candidates=urls,
        )

    @property
    def address(self) -> str:
        return content_address(self.to_dict())

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "visibility": self.visibility,
            "records": [record.to_dict() for record in self.records],
            "chant_candidates": [item.to_dict() for item in self.chant_candidates],
            "url_candidates": [item.to_dict() for item in self.url_candidates],
        }


@dataclass(frozen=True, slots=True)
class DialResult:
    kind: ClassVar[str] = "dial-result"
    status: Literal["resolved", "ambiguous", "unreachable"]
    query_kind: Literal["id", "url", "chant", "undisclosed"]
    candidates: tuple[DialIndexEntry, ...]
    record: DialRecord | None

    @classmethod
    def unreachable(cls) -> DialResult:
        return cls("unreachable", "undisclosed", (), None)

    @classmethod
    def from_dict(cls, value: Any) -> DialResult:
        obj = _fixed_header(
            value,
            cls.kind,
            {"status", "query_kind", "candidates", "record"},
        )
        status = cast(
            Literal["resolved", "ambiguous", "unreachable"],
            _literal(
                obj["status"],
                {"resolved", "ambiguous", "unreachable"},
                field="dial result status",
            ),
        )
        query_kind = cast(
            Literal["id", "url", "chant", "undisclosed"],
            _literal(
                obj["query_kind"],
                {"id", "url", "chant", "undisclosed"},
                field="dial query kind",
            ),
        )
        candidates = tuple(
            DialIndexEntry.from_dict(item)
            for item in _array(obj["candidates"], field="dial candidates")
        )
        record_value = obj["record"]
        record = None if record_value is None else DialRecord.from_dict(record_value)
        if status == "unreachable" and (
            query_kind != "undisclosed" or candidates or record is not None
        ):
            raise ValidationError("unreachable dial result must not disclose target details")
        if status == "resolved" and (record is None or len(candidates) != 1):
            raise ValidationError("resolved dial result must contain one record and candidate")
        if status == "ambiguous" and (record is not None or len(candidates) < 2):
            raise ValidationError("ambiguous dial result must contain at least two candidates")
        return cls(status, query_kind, candidates, record)

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "query_kind": self.query_kind,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "record": None if self.record is None else self.record.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    kind: ClassVar[str] = "local-subscription-plan"
    plan_id: str
    action: Literal["create-local-subscription"]
    card_id: str
    subscription: LocalSubscription
    adapter_plan: AdapterPlan | None
    undo_action: Literal["remove-local-subscription"]

    @staticmethod
    def _body(
        *,
        card_id: str,
        subscription: LocalSubscription,
        adapter_plan: AdapterPlan | None,
    ) -> JsonObject:
        return {
            "kind": "local-subscription-plan-body",
            "schema_version": SCHEMA_VERSION,
            "action": "create-local-subscription",
            "card_id": card_id,
            "subscription": subscription.to_dict(),
            "adapter_plan": None if adapter_plan is None else adapter_plan.to_dict(),
            "undo_action": "remove-local-subscription",
        }

    @classmethod
    def create(
        cls,
        *,
        card_id: str,
        subscription: LocalSubscription,
        adapter_plan: AdapterPlan | None,
    ) -> SubscriptionPlan:
        body = cls._body(
            card_id=validate_address(card_id, field="join card id"),
            subscription=subscription,
            adapter_plan=adapter_plan,
        )
        plan = cls(
            plan_id=content_address(body),
            action="create-local-subscription",
            card_id=cast(str, body["card_id"]),
            subscription=subscription,
            adapter_plan=adapter_plan,
            undo_action="remove-local-subscription",
        )
        return cls.from_dict(plan.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> SubscriptionPlan:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "plan_id",
                "action",
                "card_id",
                "subscription",
                "adapter_plan",
                "undo_action",
            },
        )
        if obj["action"] != "create-local-subscription":
            raise ValidationError("subscription plan action must create a local subscription")
        if obj["undo_action"] != "remove-local-subscription":
            raise ValidationError("subscription plan must declare its reversible action")
        card_id = validate_address(obj["card_id"], field="join card id")
        subscription = LocalSubscription.from_dict(obj["subscription"])
        adapter_value = obj["adapter_plan"]
        adapter_plan = None if adapter_value is None else AdapterPlan.from_dict(adapter_value)
        if adapter_plan is not None and subscription.adapter_plan_address != adapter_plan.address:
            raise ValidationError("subscription and adapter plan addresses do not match")
        body = cls._body(
            card_id=card_id,
            subscription=subscription,
            adapter_plan=adapter_plan,
        )
        return cls(
            plan_id=_check_body_id(obj["plan_id"], body, field="subscription plan id"),
            action="create-local-subscription",
            card_id=card_id,
            subscription=subscription,
            adapter_plan=adapter_plan,
            undo_action="remove-local-subscription",
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "action": self.action,
            "card_id": self.card_id,
            "subscription": self.subscription.to_dict(),
            "adapter_plan": None if self.adapter_plan is None else self.adapter_plan.to_dict(),
            "undo_action": self.undo_action,
        }


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    kind: ClassVar[str] = "bootstrap-result"
    status: Literal["planned", "applied", "blocked", "unreachable"]
    card_id: str
    record_id: str | None
    blocker: str | None
    candidate_ids: tuple[str, ...]
    plan: SubscriptionPlan | None
    subscription_address: str | None

    @classmethod
    def from_dict(cls, value: Any) -> BootstrapResult:
        obj = _fixed_header(
            value,
            cls.kind,
            {
                "status",
                "card_id",
                "record_id",
                "blocker",
                "candidate_ids",
                "plan",
                "subscription_address",
            },
        )
        status = cast(
            Literal["planned", "applied", "blocked", "unreachable"],
            _literal(
                obj["status"],
                {"planned", "applied", "blocked", "unreachable"},
                field="bootstrap status",
            ),
        )
        card_id = validate_address(obj["card_id"], field="bootstrap card id")
        record_value = obj["record_id"]
        record_id = (
            None
            if record_value is None
            else validate_address(record_value, field="bootstrap record id")
        )
        blocker = _nullable_string(obj["blocker"], field="bootstrap blocker")
        candidate_ids = tuple(
            validate_address(item, field="bootstrap candidate id")
            for item in _sorted_unique_strings(
                obj["candidate_ids"], field="bootstrap candidate ids"
            )
        )
        plan_value = obj["plan"]
        plan = None if plan_value is None else SubscriptionPlan.from_dict(plan_value)
        subscription_value = obj["subscription_address"]
        subscription_address = (
            None
            if subscription_value is None
            else validate_address(subscription_value, field="bootstrap subscription address")
        )
        if status == "unreachable" and (
            record_id is not None
            or blocker is not None
            or candidate_ids
            or plan is not None
            or subscription_address is not None
        ):
            raise ValidationError("unreachable bootstrap result must not disclose target details")
        if status == "blocked" and (blocker is None or plan is not None):
            raise ValidationError("blocked bootstrap result requires exactly one blocker")
        if status == "blocked":
            if blocker == "ambiguous-dial" and len(candidate_ids) < 2:
                raise ValidationError("ambiguous bootstrap blocker requires candidates")
            if blocker != "ambiguous-dial" and candidate_ids:
                raise ValidationError("only an ambiguous bootstrap blocker may list candidates")
        if status == "planned" and (plan is None or blocker is not None):
            raise ValidationError("planned bootstrap result requires a plan and no blocker")
        if status == "applied" and (
            plan is None or blocker is not None or subscription_address is None
        ):
            raise ValidationError("applied bootstrap result requires plan and subscription address")
        if status in {"planned", "applied"} and record_id is None:
            raise ValidationError("successful bootstrap result requires a record id")
        return cls(
            status=status,
            card_id=card_id,
            record_id=record_id,
            blocker=blocker,
            candidate_ids=candidate_ids,
            plan=plan,
            subscription_address=subscription_address,
        )

    def to_dict(self) -> JsonObject:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "card_id": self.card_id,
            "record_id": self.record_id,
            "blocker": self.blocker,
            "candidate_ids": list(self.candidate_ids),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "subscription_address": self.subscription_address,
        }


CONTRACT_TYPES: dict[str, type[Any]] = {
    ConformanceContract.kind: ConformanceContract,
    ProtocolDeclaration.kind: ProtocolDeclaration,
    ProtocolFingerprint.kind: ProtocolFingerprint,
    LearningBundle.kind: LearningBundle,
    AdapterRegistration.kind: AdapterRegistration,
    AdapterPlan.kind: AdapterPlan,
    AdapterRegistrationReceipt.kind: AdapterRegistrationReceipt,
    ChantLocator.kind: ChantLocator,
    DialRecord.kind: DialRecord,
    PrivateAccessPolicy.kind: PrivateAccessPolicy,
    AIJoinCard.kind: AIJoinCard,
    LocalSubscription.kind: LocalSubscription,
    "public-dialbook-index": DialbookIndex,
    "private-dialbook-index": DialbookIndex,
    DialResult.kind: DialResult,
    SubscriptionPlan.kind: SubscriptionPlan,
    BootstrapResult.kind: BootstrapResult,
}


def parse_contract(value: Any, *, expected_kind: str | None = None) -> Any:
    obj = _object(value)
    kind = obj.get("kind")
    if not isinstance(kind, str):
        raise ValidationError("contract kind must be a string")
    if expected_kind is not None and kind != expected_kind:
        raise ValidationError(f"expected contract kind {expected_kind}, got {kind}")
    contract_type = CONTRACT_TYPES.get(kind)
    if contract_type is None:
        raise ValidationError(f"unknown contract kind: {kind}")
    return contract_type.from_dict(obj)
