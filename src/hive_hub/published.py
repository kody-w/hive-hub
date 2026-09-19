from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import address_digest, canonical_bytes, content_address
from .chant import derive_chant
from .contracts import (
    AdapterRegistration,
    DialRecord,
    LearningBundle,
    ProtocolDeclaration,
    _closed,
    validate_record_contracts,
)
from .errors import ValidationError
from .limits import MAX_RECORD_BYTES

_ENVELOPE_FIELDS = {
    "$schema", "access", "adapter", "aliases", "chantProtocol", "chantProtocolFingerprint",
    "chants", "claims", "conformance", "coreContracts", "coreRecord", "dialId", "displayName",
    "kind", "learningBundle", "locator", "protocol", "protocolFingerprint", "recordId",
    "security", "summary", "visibility",
}


def project_published_record(value: Any) -> DialRecord:
    """Extract a closed core record without reinterpreting its identity body."""
    canonical_bytes(value, max_bytes=MAX_RECORD_BYTES - 1)
    envelope = _closed(value, required=_ENVELOPE_FIELDS, field="published record")
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
    if envelope["displayName"] != record.name or envelope["summary"] != record.description:
        raise ValidationError("published display text does not match coreRecord")
    access = _closed(
        envelope["access"],
        required={"authorization", "mode", "unreachableResponse"},
        field="published access",
    )
    if access["mode"] != "acl-only" or access["authorization"] != "existing-source-acl":
        raise ValidationError("public imports require existing-source-acl and acl-only")
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
