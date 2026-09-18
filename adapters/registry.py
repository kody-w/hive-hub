"""Exact adapter registry with an inert unknown-protocol result."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    AdapterRefusal,
    DeclaredAdapter,
    require,
)


@dataclass(frozen=True)
class InertProtocolAdapter:
    requested_fingerprint: str
    outcome: AccessOutcome = AccessOutcome.INERT
    fallback_used: bool = False

    def invoke(self, *_args: object, **_kwargs: object) -> None:
        raise AdapterRefusal(
            "unsupported-protocol",
            "No exact adapter is registered for this protocol fingerprint.",
        )


class AdapterRegistry:
    """Maps exact fingerprints only; it never routes unknowns to RAPP."""

    def __init__(self, adapters: tuple[DeclaredAdapter, ...] = ()) -> None:
        self._adapters: dict[str, DeclaredAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: DeclaredAdapter) -> None:
        require(
            isinstance(adapter, DeclaredAdapter),
            "invalid-adapter",
            "Registered objects must expose an adapter declaration.",
        )
        fingerprint = adapter.declaration.fingerprint.value
        require(
            fingerprint not in self._adapters,
            "duplicate-adapter",
            "An adapter is already registered for this exact fingerprint.",
        )
        self._adapters[fingerprint] = adapter

    def resolve(self, fingerprint: str) -> DeclaredAdapter | InertProtocolAdapter:
        return self._adapters.get(fingerprint) or InertProtocolAdapter(fingerprint)

    def declarations(self) -> tuple[AdapterDeclaration, ...]:
        return tuple(
            adapter.declaration for _, adapter in sorted(self._adapters.items())
        )
