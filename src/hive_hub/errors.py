from __future__ import annotations

from typing import Any


class HiveHubError(Exception):
    """Base error with a stable, machine-readable code."""

    code = "hive-hub-error"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        return {"ok": False, "error": error}


class ValidationError(HiveHubError):
    code = "validation-error"


class StorageError(HiveHubError):
    code = "storage-error"


class ConflictError(HiveHubError):
    code = "conflict"


class NotFoundError(HiveHubError):
    code = "not-found"


class UnsafePathError(HiveHubError):
    code = "unsafe-path"


class LimitError(HiveHubError):
    code = "limit-exceeded"
