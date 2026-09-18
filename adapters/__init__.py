"""Protocol-neutral Hive Hub adapters."""

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    AdapterRefusal,
    CapabilityRequirement,
    ConformanceContract,
    LearningBundle,
    LearningDocument,
    PrivateAccessMode,
    ProtocolFingerprint,
    RequirementLevel,
)
from .defaults import build_default_registry
from .filesystem import LocalFilesystemWorkspaceAdapter
from .github import GitHubRepositoryAdapter
from .legacy_hub import LegacyRappHubInspector
from .payphone import PayphoneAdapter, door_from_rappid
from .rapp import RappDelegatingAdapter, RappToolKind
from .rappid import RappidChantAdapter
from .registry import AdapterRegistry, InertProtocolAdapter

__all__ = [
    "AccessOutcome",
    "AdapterDeclaration",
    "AdapterRefusal",
    "AdapterRegistry",
    "CapabilityRequirement",
    "ConformanceContract",
    "GitHubRepositoryAdapter",
    "InertProtocolAdapter",
    "LearningBundle",
    "LearningDocument",
    "LegacyRappHubInspector",
    "LocalFilesystemWorkspaceAdapter",
    "PayphoneAdapter",
    "PrivateAccessMode",
    "ProtocolFingerprint",
    "RappDelegatingAdapter",
    "RappToolKind",
    "RappidChantAdapter",
    "RequirementLevel",
    "build_default_registry",
    "door_from_rappid",
]
