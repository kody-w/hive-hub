from __future__ import annotations

import shutil
import unittest
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from hive_hub import (
    AdapterRegistration,
    ConformanceContract,
    ConformanceRequirement,
    DialRecord,
    HiveHub,
    LearningArtifact,
    LearningBundle,
    ProtocolDeclaration,
)

PROJECT_ROOT = Path(__file__).parents[1]
WORK_ROOT = PROJECT_ROOT / "tests" / ".work"
FIXED_TIME = "2026-09-18T19:16:11Z"


class WorkspaceTestCase(unittest.TestCase):
    work: Path

    def setUp(self) -> None:
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        self.work = WORK_ROOT / f"{self.__class__.__name__}-{uuid.uuid4().hex}"
        self.work.mkdir(mode=0o700)

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)


@dataclass(frozen=True)
class GenericStack:
    hub: HiveHub
    conformance: ConformanceContract
    declaration: ProtocolDeclaration
    bundle: LearningBundle
    adapter: AdapterRegistration


def make_stack(
    home: Path,
    *,
    effect_kinds: tuple[str, ...] = (),
    register_adapter: bool = True,
) -> GenericStack:
    conformance = ConformanceContract.create(
        version="1.0",
        requirements=[
            ConformanceRequirement("decode-envelope", "Decode a Firefly envelope."),
            ConformanceRequirement("preserve-order", "Preserve event ordering."),
        ],
    )
    declaration = ProtocolDeclaration.create(
        name="Firefly Mesh",
        protocol_version="7.2",
        media_type="application/vnd.firefly.mesh+json",
        capabilities=["discover", "join", "observe"],
        conformance_address=conformance.address,
    )
    bundle = LearningBundle.create(
        protocol_fingerprint=declaration.fingerprint,
        bundle_version="2026.09",
        summary="A protocol-neutral learning bundle for Firefly Mesh.",
        conformance_contract=conformance,
        artifacts=[
            LearningArtifact.create(
                name="examples/envelope.json",
                media_type="application/json",
                content='{"event":"glow","sequence":1}',
            ),
            LearningArtifact.create(
                name="protocol.txt",
                media_type="text/plain",
                content="Firefly Mesh documents are inert UTF-8 data.",
            ),
        ],
    )
    adapter = AdapterRegistration.create(
        protocol_fingerprint=declaration.fingerprint,
        name="Firefly local adapter",
        adapter_version="3.0",
        locator="urn:firefly:adapter:local-v3",
        conformance_address=conformance.address,
        operations=["authorize", "fetch", "subscribe"],
        effect_kinds=effect_kinds,
    )
    hub = HiveHub(home)
    hub.learn_protocol(declaration, bundle)
    if register_adapter:
        hub.register_adapter(adapter, registered_at=FIXED_TIME)
    return GenericStack(hub, conformance, declaration, bundle, adapter)


def make_record(
    stack: GenericStack,
    *,
    visibility: str = "public",
    name: str = "Firefly Commons",
    url: str = "https://firefly.invalid/hives/commons",
    chant: str = "firefly commons",
) -> DialRecord:
    return DialRecord.create(
        name=name,
        description="A non-RAPP protocol example.",
        visibility=visibility,  # type: ignore[arg-type]
        protocol_fingerprint=stack.declaration.fingerprint,
        learning_bundle_address=stack.bundle.address,
        adapter_registration_address=stack.adapter.address,
        urls=[url],
        chants=[chant],
    )


def files_under(path: Path) -> Iterator[Path]:
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            yield item
