"""Construction of the complete exact-fingerprint adapter registry."""

from __future__ import annotations

from .filesystem import LocalFilesystemWorkspaceAdapter
from .github import GitHubRepositoryAdapter
from .legacy_hub import LegacyRappHubInspector
from .payphone import PayphoneAdapter
from .rapp import RappDelegatingAdapter
from .rappid import RappidChantAdapter
from .registry import AdapterRegistry


def build_default_registry(
    *,
    rapp_adapter: RappDelegatingAdapter | None = None,
) -> AdapterRegistry:
    return AdapterRegistry(
        (
            GitHubRepositoryAdapter(),
            LocalFilesystemWorkspaceAdapter(),
            rapp_adapter or RappDelegatingAdapter.discover(),
            RappidChantAdapter(),
            PayphoneAdapter(),
            LegacyRappHubInspector(),
        )
    )
