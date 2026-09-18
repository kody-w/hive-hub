from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import NotFoundError

ADDRESS = {
    "type": "string",
    "pattern": r"^urn:hivehub:sha256:[0-9a-f]{64}$",
}
NONEMPTY = {"type": "string", "minLength": 1, "maxLength": 4096}
NULLABLE_ADDRESS = {"oneOf": [ADDRESS, {"type": "null"}]}
HEADER = {
    "kind": {"type": "string"},
    "schema_version": {"const": 1},
}
PRINCIPAL = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "id"],
    "properties": {
        "kind": {"enum": ["human", "ai"]},
        "id": NONEMPTY,
    },
}
REQUIREMENT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "description"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9._-]*$"},
        "description": {"type": "string"},
    },
}
CONFORMANCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "schema_version", "version", "requirements"],
    "properties": {
        **HEADER,
        "kind": {"const": "conformance-contract"},
        "version": NONEMPTY,
        "requirements": {
            "type": "array",
            "maxItems": 256,
            "items": REQUIREMENT,
        },
    },
}
ARTIFACT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "media_type", "encoding", "content", "content_address"],
    "properties": {
        "name": NONEMPTY,
        "media_type": NONEMPTY,
        "encoding": {"const": "utf-8"},
        "content": {"type": "string"},
        "content_address": ADDRESS,
    },
}
ADAPTER_EFFECT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["effect_id", "kind", "description", "locator", "requires_approval"],
    "properties": {
        "effect_id": NONEMPTY,
        "kind": {"enum": ["authenticate", "clone", "execute", "fetch", "other", "write"]},
        "description": NONEMPTY,
        "locator": {"oneOf": [NONEMPTY, {"type": "null"}]},
        "requires_approval": {"const": True},
    },
}
ADAPTER_PLAN = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "schema_version",
        "adapter_registration_address",
        "record_id",
        "effects",
    ],
    "properties": {
        **HEADER,
        "kind": {"const": "adapter-plan"},
        "adapter_registration_address": ADDRESS,
        "record_id": ADDRESS,
        "effects": {"type": "array", "maxItems": 256, "items": ADAPTER_EFFECT},
    },
}
DIAL_INDEX_ENTRY = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "name",
        "protocol_fingerprint",
        "learning_bundle_address",
        "adapter_registration_address",
        "urls",
        "chants",
    ],
    "properties": {
        "id": ADDRESS,
        "name": NONEMPTY,
        "protocol_fingerprint": ADDRESS,
        "learning_bundle_address": ADDRESS,
        "adapter_registration_address": ADDRESS,
        "urls": {"type": "array", "maxItems": 256, "items": NONEMPTY},
        "chants": {"type": "array", "maxItems": 256, "items": NONEMPTY},
    },
}
CANDIDATE_SET = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidate", "record_ids"],
    "properties": {
        "candidate": NONEMPTY,
        "record_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": ADDRESS,
        },
    },
}
DIAL_RECORD = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "schema_version",
        "id",
        "name",
        "description",
        "visibility",
        "protocol_fingerprint",
        "learning_bundle_address",
        "adapter_registration_address",
        "urls",
        "chants",
    ],
    "properties": {
        **HEADER,
        "kind": {"const": "dial-record"},
        "id": ADDRESS,
        "name": NONEMPTY,
        "description": {"type": "string"},
        "visibility": {"enum": ["local", "public", "private"]},
        "protocol_fingerprint": ADDRESS,
        "learning_bundle_address": ADDRESS,
        "adapter_registration_address": ADDRESS,
        "urls": {"type": "array", "maxItems": 256, "items": NONEMPTY},
        "chants": {"type": "array", "maxItems": 256, "items": NONEMPTY},
    },
}
LOCAL_SUBSCRIPTION = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "schema_version",
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
    ],
    "properties": {
        **HEADER,
        "kind": {"const": "local-subscription"},
        "id": ADDRESS,
        "record_id": ADDRESS,
        "record_visibility": {"enum": ["local", "public", "private"]},
        "protocol_fingerprint": ADDRESS,
        "learning_bundle_address": ADDRESS,
        "adapter_registration_address": ADDRESS,
        "locator": NONEMPTY,
        "principal": PRINCIPAL,
        "state": {"const": "active"},
        "adapter_plan_address": NULLABLE_ADDRESS,
        "adapter_effects_status": {"enum": ["not-required", "not-executed"]},
        "created_at": NONEMPTY,
    },
}
SUBSCRIPTION_PLAN = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "kind",
        "schema_version",
        "plan_id",
        "action",
        "card_id",
        "subscription",
        "adapter_plan",
        "undo_action",
    ],
    "properties": {
        **HEADER,
        "kind": {"const": "local-subscription-plan"},
        "plan_id": ADDRESS,
        "action": {"const": "create-local-subscription"},
        "card_id": ADDRESS,
        "subscription": LOCAL_SUBSCRIPTION,
        "adapter_plan": {"oneOf": [ADAPTER_PLAN, {"type": "null"}]},
        "undo_action": {"const": "remove-local-subscription"},
    },
}


def _schema(name: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:hivehub:schema:{name}:1",
        "title": name,
        **body,
    }


def _dialbook_schema(visibility: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "kind",
            "schema_version",
            "visibility",
            "records",
            "chant_candidates",
            "url_candidates",
        ],
        "properties": {
            **HEADER,
            "kind": {"const": f"{visibility}-dialbook-index"},
            "visibility": {"const": visibility},
            "records": {"type": "array", "maxItems": 256, "items": DIAL_INDEX_ENTRY},
            "chant_candidates": {
                "type": "array",
                "maxItems": 256,
                "items": CANDIDATE_SET,
            },
            "url_candidates": {
                "type": "array",
                "maxItems": 256,
                "items": CANDIDATE_SET,
            },
        },
    }


SCHEMAS: dict[str, dict[str, Any]] = {
    "conformance-contract": _schema("conformance-contract", CONFORMANCE),
    "protocol-declaration": _schema(
        "protocol-declaration",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "name",
                "protocol_version",
                "adapter_api_version",
                "media_type",
                "capabilities",
                "conformance_address",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "protocol-declaration"},
                "name": NONEMPTY,
                "protocol_version": NONEMPTY,
                "adapter_api_version": NONEMPTY,
                "media_type": NONEMPTY,
                "capabilities": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 256,
                    "items": NONEMPTY,
                },
                "conformance_address": ADDRESS,
            },
        },
    ),
    "protocol-fingerprint": _schema(
        "protocol-fingerprint",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "schema_version", "algorithm", "value"],
            "properties": {
                **HEADER,
                "kind": {"const": "protocol-fingerprint"},
                "algorithm": {"const": "sha256"},
                "value": ADDRESS,
            },
        },
    ),
    "learning-bundle": _schema(
        "learning-bundle",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "protocol_fingerprint",
                "bundle_version",
                "summary",
                "conformance_contract",
                "artifacts",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "learning-bundle"},
                "protocol_fingerprint": ADDRESS,
                "bundle_version": NONEMPTY,
                "summary": NONEMPTY,
                "conformance_contract": CONFORMANCE,
                "artifacts": {"type": "array", "maxItems": 256, "items": ARTIFACT},
            },
        },
    ),
    "adapter-registration": _schema(
        "adapter-registration",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "protocol_fingerprint",
                "name",
                "adapter_version",
                "interface_version",
                "locator",
                "conformance_address",
                "operations",
                "effect_kinds",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "adapter-registration"},
                "protocol_fingerprint": ADDRESS,
                "name": NONEMPTY,
                "adapter_version": NONEMPTY,
                "interface_version": NONEMPTY,
                "locator": NONEMPTY,
                "conformance_address": ADDRESS,
                "operations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 256,
                    "items": NONEMPTY,
                },
                "effect_kinds": {
                    "type": "array",
                    "maxItems": 256,
                    "items": {
                        "enum": ["authenticate", "clone", "execute", "fetch", "other", "write"]
                    },
                },
            },
        },
    ),
    "adapter-registration-receipt": _schema(
        "adapter-registration-receipt",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "receipt_id",
                "registration_address",
                "protocol_fingerprint",
                "scope",
                "status",
                "registered_at",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "adapter-registration-receipt"},
                "receipt_id": ADDRESS,
                "registration_address": ADDRESS,
                "protocol_fingerprint": ADDRESS,
                "scope": {"enum": ["local", "public", "private"]},
                "status": {"const": "registered"},
                "registered_at": NONEMPTY,
            },
        },
    ),
    "adapter-plan": _schema("adapter-plan", ADAPTER_PLAN),
    "dial-record": _schema("dial-record", DIAL_RECORD),
    "local-subscription": _schema("local-subscription", LOCAL_SUBSCRIPTION),
    "ai-join-card": _schema(
        "ai-join-card",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "card_id",
                "principal",
                "locator",
                "expected_record_id",
                "expected_protocol_fingerprint",
                "adapter_plan",
                "issued_at",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "ai-join-card"},
                "card_id": ADDRESS,
                "principal": PRINCIPAL,
                "locator": NONEMPTY,
                "expected_record_id": NULLABLE_ADDRESS,
                "expected_protocol_fingerprint": NULLABLE_ADDRESS,
                "adapter_plan": {"oneOf": [ADAPTER_PLAN, {"type": "null"}]},
                "issued_at": NONEMPTY,
            },
        },
    ),
    "local-subscription-plan": _schema("local-subscription-plan", SUBSCRIPTION_PLAN),
    "bootstrap-result": _schema(
        "bootstrap-result",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "status",
                "card_id",
                "record_id",
                "blocker",
                "candidate_ids",
                "plan",
                "subscription_address",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "bootstrap-result"},
                "status": {"enum": ["planned", "applied", "blocked", "unreachable"]},
                "card_id": ADDRESS,
                "record_id": NULLABLE_ADDRESS,
                "blocker": {"oneOf": [NONEMPTY, {"type": "null"}]},
                "candidate_ids": {"type": "array", "maxItems": 256, "items": ADDRESS},
                "plan": {"oneOf": [SUBSCRIPTION_PLAN, {"type": "null"}]},
                "subscription_address": NULLABLE_ADDRESS,
            },
        },
    ),
    "public-dialbook-index": _schema("public-dialbook-index", _dialbook_schema("public")),
    "private-dialbook-index": _schema("private-dialbook-index", _dialbook_schema("private")),
    "private-access-policy": _schema(
        "private-access-policy",
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "kind",
                "schema_version",
                "record_id",
                "mode",
                "scope",
                "epoch",
                "qr_commitment",
            ],
            "properties": {
                **HEADER,
                "kind": {"const": "private-access-policy"},
                "record_id": ADDRESS,
                "mode": {"enum": ["acl-only", "acl+qr"], "default": "acl-only"},
                "scope": NONEMPTY,
                "epoch": NONEMPTY,
                "qr_commitment": NULLABLE_ADDRESS,
            },
        },
    ),
}


def schema_names() -> tuple[str, ...]:
    return tuple(sorted(SCHEMAS))


def get_schema(name: str) -> dict[str, Any]:
    try:
        return deepcopy(SCHEMAS[name])
    except KeyError as exc:
        raise NotFoundError(f"unknown schema: {name}") from exc
