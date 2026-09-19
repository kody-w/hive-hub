from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from .errors import LimitError, ValidationError
from .limits import (
    MAX_ARRAY_ITEMS,
    MAX_INTEGER,
    MAX_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_OBJECT_ITEMS,
    MAX_STRING_BYTES,
)

ADDRESS_PREFIX = "urn:hivehub:sha256:"
ADDRESS_RE = re.compile(r"^urn:hivehub:sha256:[0-9a-f]{64}$")
JsonValue = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]


def _reject_constant(value: str) -> NoReturn:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _parse_integer(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > 19:
        raise LimitError("JSON integer exceeds the signed 64-bit limit")
    parsed = int(value)
    if abs(parsed) > MAX_INTEGER:
        raise LimitError("JSON integer exceeds the signed 64-bit limit")
    return parsed


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_json_value(value: Any, *, depth: int = 0) -> JsonValue:
    if depth > MAX_JSON_DEPTH:
        raise LimitError("JSON nesting depth exceeds the configured limit")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_INTEGER:
            raise LimitError("JSON integer exceeds the signed 64-bit limit")
        return value
    if isinstance(value, float):
        raise ValidationError("floating-point JSON values are forbidden")
    if isinstance(value, str):
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValidationError("JSON strings must contain valid Unicode") from exc
        if len(encoded) > MAX_STRING_BYTES:
            raise LimitError("JSON string exceeds the configured byte limit")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_OBJECT_ITEMS:
            raise LimitError("JSON object exceeds the configured member limit")
        result: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValidationError("JSON object keys must be strings")
            if key in result:
                raise ValidationError(f"duplicate JSON key: {key}")
            result[key] = _validate_json_value(child, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_ARRAY_ITEMS:
            raise LimitError("JSON array exceeds the configured item limit")
        return [_validate_json_value(child, depth=depth + 1) for child in value]
    raise ValidationError(f"unsupported JSON value type: {type(value).__name__}")


def loads_json(data: str | bytes, *, max_bytes: int = MAX_JSON_BYTES) -> JsonValue:
    if isinstance(data, bytes):
        if len(data) > max_bytes:
            raise LimitError("JSON document exceeds the configured byte limit")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("JSON document must be UTF-8") from exc
    else:
        try:
            encoded_input = data.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValidationError("JSON document must contain valid Unicode") from exc
        if len(encoded_input) > max_bytes:
            raise LimitError("JSON document exceeds the configured byte limit")
        text = data
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=lambda _value: _reject_constant("floating-point"),
            parse_int=_parse_integer,
        )
    except ValidationError:
        raise
    except RecursionError as exc:
        raise LimitError("JSON nesting depth exceeds the configured limit") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "invalid JSON",
            detail={"line": exc.lineno, "column": exc.colno},
        ) from exc
    except ValueError as exc:
        raise ValidationError("invalid JSON numeric value") from exc
    return _validate_json_value(value)


def canonical_bytes(value: Any, *, max_bytes: int = MAX_JSON_BYTES) -> bytes:
    normalized = _validate_json_value(value)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValidationError("value cannot be encoded as canonical JSON") from exc
    if len(encoded) > max_bytes:
        raise LimitError("canonical JSON exceeds the configured byte limit")
    return encoded


def canonical_dumps(value: Any, *, max_bytes: int = MAX_JSON_BYTES) -> str:
    return canonical_bytes(value, max_bytes=max_bytes).decode("utf-8")


def content_address(value: Any, *, raw: bool = False) -> str:
    if raw:
        if not isinstance(value, bytes):
            raise TypeError("raw content addressing requires bytes")
        data = value
    else:
        data = canonical_bytes(value)
    return ADDRESS_PREFIX + hashlib.sha256(data).hexdigest()


def validate_address(value: Any, *, field: str = "content address") -> str:
    if not isinstance(value, str) or ADDRESS_RE.fullmatch(value) is None:
        raise ValidationError(f"{field} must be a canonical Hive Hub SHA-256 URN")
    return value


def address_digest(address: str) -> str:
    return validate_address(address)[len(ADDRESS_PREFIX) :]


def is_address(value: str) -> bool:
    return ADDRESS_RE.fullmatch(value) is not None
