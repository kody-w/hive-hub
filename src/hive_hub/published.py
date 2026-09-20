from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .canonical import address_digest, canonical_bytes, content_address
from .chant import derive_chant
from .contracts import (
    AdapterRegistration,
    DialRecord,
    LearningBundle,
    ProtocolDeclaration,
    _array,
    _closed,
    _object,
    _string,
    validate_locator,
    validate_record_contracts,
)
from .errors import ValidationError
from .limits import MAX_PATH_DEPTH, MAX_RECORD_BYTES

_ENVELOPE_FIELDS = {
    "$schema", "access", "adapter", "aliases", "chantProtocol", "chantProtocolFingerprint",
    "chants", "claims", "conformance", "coreContracts", "coreRecord", "dialId", "displayName",
    "kind", "learningBundle", "locator", "protocol", "protocolFingerprint", "recordId",
    "security", "summary", "visibility",
}
_SHA256_REF = re.compile(r"sha256:[0-9a-f]{64}")
_ALIAS = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _https_url(value: Any, *, field: str) -> str:
    url = validate_locator(value, field=field)
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError(f"{field} must be a valid HTTPS URL") from exc
    if (
        not url.startswith("https://") or parsed.query or port == 0
        or any(character.isspace() for character in url)
        or "\\" in url or "%" in url
    ):
        raise ValidationError(f"{field} must be an unambiguous credential-free HTTPS URL")
    return url


def _public_path(value: Any, *, field: str) -> str:
    path = _string(value, field=field)
    parts = path.split("/")
    if (
        len(parts) > MAX_PATH_DEPTH or ".." in path
        or any(part in {"", "."} for part in parts)
        or any(character in path for character in "\\%:#?")
        or any(character.isspace() for character in path)
    ):
        raise ValidationError(f"{field} must be a safe relative public path")
    return path


def _sha256_ref(value: Any, *, field: str) -> str:
    reference = _string(value, field=field)
    if _SHA256_REF.fullmatch(reference) is None:
        raise ValidationError(f"{field} must be a SHA-256 content reference")
    return reference


def _descriptor(value: Any, *, field: str) -> dict[str, Any]:
    descriptor = _closed(value, required={"path", "ref", "url"}, field=field)
    path = _public_path(descriptor["path"], field=f"{field} path")
    _sha256_ref(descriptor["ref"], field=f"{field} ref")
    url = _https_url(descriptor["url"], field=f"{field} URL")
    url_path = urlsplit(url).path
    _public_path(url_path.removeprefix("/"), field=f"{field} URL path")
    if not url_path.endswith("/" + path):
        raise ValidationError(f"{field} URL does not match its public path")
    return descriptor


def published_locator_urls(value: Any) -> tuple[str, ...]:
    """Use the same locator projection when publishing and importing core URLs."""
    locator = _object(value, field="published locator")
    urls: set[str] = set()
    for key, child in locator.items():
        if key == "url" or key.endswith("Url"):
            urls.add(validate_locator(child, field="published locator URL"))
        elif isinstance(child, dict):
            urls.update(published_locator_urls(child))
    return tuple(sorted(urls))


def _validate_presentation(envelope: dict[str, Any]) -> None:
    _https_url(envelope["$schema"], field="published schema")
    _string(envelope["recordId"], field="published recordId")
    aliases = _array(envelope["aliases"], field="published aliases")
    if not aliases:
        raise ValidationError("published aliases must contain at least one label")
    for value in aliases:
        if _ALIAS.fullmatch(_string(value, field="published alias")) is None:
            raise ValidationError("published aliases must be lowercase slug labels")
    for key in ("adapter", "conformance", "protocol", "learningBundle", "chantProtocol"):
        _descriptor(envelope[key], field=f"published {key}")
    for key in ("protocol", "chantProtocol"):
        fingerprint = _sha256_ref(
            envelope[key + "Fingerprint"], field=f"published {key} fingerprint"
        )
        if fingerprint != envelope[key]["ref"]:
            raise ValidationError(f"published {key} fingerprint does not match its descriptor")


def project_published_record(value: Any) -> DialRecord:
    """Extract a closed core record without reinterpreting its identity body."""
    canonical_bytes(value, max_bytes=MAX_RECORD_BYTES - 1)
    envelope = _closed(value, required=_ENVELOPE_FIELDS, field="published record")
    _validate_presentation(envelope)
    record = DialRecord.from_dict(envelope["coreRecord"])
    if canonical_bytes(envelope["coreRecord"]) != canonical_bytes(record.to_dict()):
        raise ValidationError("published coreRecord must use its canonical contract values")
    if (
        envelope["kind"] != "dial-record"
        or envelope["visibility"] != "public"
        or record.visibility != "public"
    ):
        raise ValidationError("published record must be a public DialRecord")
    if envelope["dialId"] != record.dial_id:
        raise ValidationError("published dialId does not match the core identity body")
    if envelope["chants"] != [
        {"role": "candidate-locator-only", "value": derive_chant(record.dial_id)}
    ]:
        raise ValidationError("published chant does not match the core Dial Record ID")
    if record.chants not in ((), (derive_chant(record.dial_id),)):
        raise ValidationError("imported core chants must be empty or the ID-derived chant")
    if record.urls != published_locator_urls(envelope["locator"]):
        raise ValidationError("imported core URLs do not match the published locator")
    if envelope["displayName"] != record.name or envelope["summary"] != record.description:
        raise ValidationError("published display text does not match coreRecord")
    access = _closed(
        envelope["access"],
        required={"authorization", "mode", "unreachableResponse"},
        field="published access",
    )
    if access["mode"] != "acl-only" or access["authorization"] != "existing-source-acl":
        raise ValidationError("public imports require existing-source-acl and acl-only")
    _string(access["unreachableResponse"], field="published unreachable response")
    if envelope["claims"] != {"authority": [], "semanticCompatibility": []}:
        raise ValidationError("published discovery cannot grant authority or compatibility")
    security = _closed(
        envelope["security"],
        required={"credentialsIncluded", "retrievedContent"}, field="published security",
    )
    if (
        security["credentialsIncluded"] is not False
        or security["retrievedContent"] != "inert-until-approved-and-verified"
    ):
        raise ValidationError("published discovery must remain credential-free and inert")
    return record


@dataclass(frozen=True, slots=True)
class PublishedRecord:
    record: DialRecord
    declaration: ProtocolDeclaration
    bundle: LearningBundle
    adapter: AdapterRegistration

    @classmethod
    def from_dict(cls, value: Any) -> PublishedRecord:
        record = project_published_record(value)
        contracts = _closed(
            value["coreContracts"],
            required={"protocol", "learningBundle", "adapter"},
            field="published coreContracts",
        )
        declaration = ProtocolDeclaration.from_dict(contracts["protocol"])
        bundle = LearningBundle.from_dict(contracts["learningBundle"])
        adapter = AdapterRegistration.from_dict(contracts["adapter"])
        for name, document in (
            ("protocol", declaration), ("learningBundle", bundle), ("adapter", adapter)
        ):
            if canonical_bytes(contracts[name]) != canonical_bytes(document.to_dict()):
                raise ValidationError("published contracts must use canonical values")
        validate_record_contracts(record, declaration, bundle, adapter)
        artifacts = {artifact.name: artifact for artifact in bundle.artifacts}
        for key, name in (
            ("protocol", "protocol.json"), ("conformance", "conformance.json"),
            ("learningBundle", "learning-bundle.json"), ("adapter", "adapter.json"),
        ):
            descriptor = _closed(
                value[key], required={"path", "ref", "url"}, field="published descriptor"
            )
            artifact = artifacts.get(name)
            if artifact is None or descriptor["ref"] != (
                "sha256:" + address_digest(artifact.content_address)
            ):
                raise ValidationError("published descriptor does not match its inert artifact")
        locator = artifacts.get("locator.json")
        if locator is None or locator.content_address != content_address(
            canonical_bytes(value["locator"]) + b"\n", raw=True
        ):
            raise ValidationError("published locator does not match its inert artifact")
        if adapter.locator != value["adapter"]["url"]:
            raise ValidationError("published adapter locator does not match its registration")
        return cls(record, declaration, bundle, adapter)
