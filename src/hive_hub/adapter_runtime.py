from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any

from .canonical import content_address
from .contracts import (
    AdapterRegistration,
    ConformanceContract,
    ConformanceRequirement,
    LearningArtifact,
    LearningBundle,
    ProtocolDeclaration,
)
from .errors import NotFoundError

ADAPTER_RELEASE_VERSION = "0.1.1"


@dataclass(frozen=True, slots=True)
class BuiltinAdapterContracts:
    adapter_id: str
    source_fingerprint: str
    declaration: ProtocolDeclaration
    learning_bundle: LearningBundle
    registration: AdapterRegistration

    def _identity(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "source_fingerprint": self.source_fingerprint,
            "protocol_fingerprint": self.declaration.fingerprint,
            "learning_bundle_address": self.learning_bundle.address,
            "adapter_registration_address": self.registration.address,
        }

    def plan_body(self) -> dict[str, Any]:
        return {
            "kind": "builtin-adapter-install-plan",
            "schema_version": 1,
            "adapter": self._identity(),
            "effects": [
                {
                    "kind": "local-write",
                    "description": (
                        "Store inert protocol, learning, adapter, and receipt contracts."
                    ),
                    "requires_approval": True,
                }
            ],
            "adapter_execution": False,
        }

    @property
    def plan_id(self) -> str:
        return content_address(self.plan_body())

    def summary(self) -> dict[str, Any]:
        return {
            **self._identity(),
            "install_plan_id": self.plan_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "builtin-adapter-contracts",
            "schema_version": 1,
            **self.summary(),
            "protocol_declaration": self.declaration.to_dict(),
            "learning_bundle": self.learning_bundle.to_dict(),
            "adapter_registration": self.registration.to_dict(),
        }


_OPERATIONS = {
    "github-repository": ("probe",),
    "legacy-rapp-hub-inspector": ("inspect",),
    "local-filesystem-workspace": ("probe",),
    "rapp-authority-delegate": ("describe", "inspect", "learn", "probe", "read", "verify"),
    "rapp-payphone": ("derive", "dial", "resolve"),
    "rappid-seven-word-chant": ("derive", "resolve"),
}

_EFFECTS = {
    "github-repository": ("fetch",),
    "rapp-authority-delegate": ("other",),
}


def _adapter_modules() -> tuple[ModuleType | None, ModuleType | None]:
    try:
        defaults = import_module("adapters.defaults")
        rapp = import_module("adapters.rapp")
    except ModuleNotFoundError as exc:
        if exc.name == "adapters" or (exc.name or "").startswith("adapters."):
            return None, None
        raise
    return defaults, rapp


def adapters_available() -> bool:
    defaults, _ = _adapter_modules()
    return defaults is not None


def builtin_adapter_contracts() -> tuple[BuiltinAdapterContracts, ...]:
    defaults, rapp = _adapter_modules()
    if defaults is None or rapp is None:
        return ()
    registry = defaults.build_default_registry(
        rapp_adapter=rapp.RappDelegatingAdapter(),
    )
    bundles: list[BuiltinAdapterContracts] = []
    for source in registry.declarations():
        requirements = tuple(
            ConformanceRequirement(
                requirement_id=assertion,
                description=f"Required by {source.conformance.profile}.",
            )
            for assertion in source.conformance.assertions
        )
        conformance = ConformanceContract.create(
            version=source.conformance.profile,
            requirements=requirements,
        )
        declaration = ProtocolDeclaration.create(
            name=source.adapter_id,
            protocol_version=source.fingerprint.protocol,
            media_type="application/json",
            capabilities=tuple(
                requirement.capability for requirement in source.capabilities
            ),
            conformance_address=conformance.address,
        )
        artifacts = tuple(
            LearningArtifact.create(
                name=document.name,
                media_type=document.media_type,
                content=document.content,
            )
            for document in source.learning_bundle.documents
        )
        learning_bundle = LearningBundle.create(
            protocol_fingerprint=declaration.fingerprint,
            bundle_version=ADAPTER_RELEASE_VERSION,
            summary=source.authority_model,
            conformance_contract=conformance,
            artifacts=artifacts,
        )
        registration = AdapterRegistration.create(
            protocol_fingerprint=declaration.fingerprint,
            name=source.adapter_id,
            adapter_version=ADAPTER_RELEASE_VERSION,
            locator=(
                "urn:hivehub:adapter:"
                f"{source.adapter_id}:sha256:{source.fingerprint.contract_sha256}"
            ),
            conformance_address=conformance.address,
            operations=_OPERATIONS[source.adapter_id],
            effect_kinds=_EFFECTS.get(source.adapter_id, ()),
        )
        bundles.append(
            BuiltinAdapterContracts(
                adapter_id=source.adapter_id,
                source_fingerprint=source.fingerprint.value,
                declaration=declaration,
                learning_bundle=learning_bundle,
                registration=registration,
            )
        )
    return tuple(sorted(bundles, key=lambda item: item.adapter_id))


def get_builtin_adapter(adapter_id: str) -> BuiltinAdapterContracts:
    for contracts in builtin_adapter_contracts():
        if contracts.adapter_id == adapter_id:
            return contracts
    raise NotFoundError("built-in adapter is not available")


def builtin_install_plan(contracts: BuiltinAdapterContracts) -> dict[str, Any]:
    return {
        **contracts.plan_body(),
        "plan_id": contracts.plan_id,
    }
