"""Build examples/hive-md/: the experimental hive-md protocol and the synthetic Contoso model Hive.

Every value is fixed, so the output is byte-for-byte reproducible. From the repository root:

    PYTHONPATH=src:. python examples/build_hive_md.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.hive_md import (
    CHECKER_COMMAND,
    CHECKER_PATH,
    CHECKER_SHA256,
    CONVENTION_COMMIT,
    CONVENTION_REPOSITORY,
    CONVENTION_SPEC_PATH,
    CONVENTION_SPEC_SHA256,
    HIVE_MD_DECLARATION,
    HIVE_MD_FINGERPRINT,
    HIVE_MD_NAME,
    HIVE_MD_VERSION,
    PINS_ARTIFACT,
    HiveMdDialPinAdapter,
    HiveMdDialPins,
)
from hive_hub import (
    AdapterEffect,
    AdapterPlan,
    AdapterRegistration,
    AIJoinCard,
    ConformanceContract,
    ConformanceRequirement,
    DialRecord,
    LearningArtifact,
    LearningBundle,
    Principal,
    ProtocolDeclaration,
    ProtocolFingerprint,
    canonical_bytes,
    derive_chant,
)
from hive_hub.contracts import validate_record_contracts

TARGET = Path(__file__).parent / "hive-md"
FIXED_TIME = "2026-09-24T09:00:00Z"
AT_COMMIT = f"kody-w/rapp-model-hive@{CONVENTION_COMMIT}"

# The synthetic Contoso model Hive from kody-w/rapp-model-hive (example/HISTORY.md). Avery founded
# it with a public test key derived from a published label. It is a published snapshot with no
# live shared copy, so its address uses the reserved .invalid domain and resolves nowhere.
CONTOSO_PINS = HiveMdDialPins(
    address="https://contoso.invalid/hives/contoso-onboarding.git",
    hive="185d0eb5d4b1247b260042d0d840d5c3",
    root="f934db89e0c73d71843d634b8ddbd53154732735",
    founder="SHA256:q18VTrWDieC+Sc25wpbcIHm4/gUotkmUJpyFgDeOdyY",
    public_copy=(
        f"{CONVENTION_REPOSITORY}/tree/{CONVENTION_COMMIT}/example/contoso-onboarding-public"
    ),
)

FOLDER_HIVE_TEXT = f"""# hive-md: a folder Hive (experimental)

A folder Hive is a git repository of markdown files: `HIVE.md` holds its rules,
`members/<name>/` is each member's space with device keys in
`members/<name>/keys/<device>.md`, `requests/` holds requests to join, `shared/`
holds the rooms and `former/` the spaces of members who left. Every change is an
SSH-signed commit, judged by the Hive as it stood at its parent. Transport carries;
signatures decide.

The convention is `{CONVENTION_SPEC_PATH}` at `{AT_COMMIT}`
(SHA-256 `{CONVENTION_SPEC_SHA256}`). Its checker is `{CHECKER_PATH}`
(SHA-256 `{CHECKER_SHA256}`): `{CHECKER_COMMAND}`.

## Dial pins

`{PINS_ARTIFACT}` holds exactly these pins:

- `address`: the shared copy's git URL (ssh, https or git). It may be private. It is
  never a local path and never carries a user name, password or token.
- `hive`: the Hive id from `HIVE.md` (32 lowercase hexadecimal characters).
- `root`: the full id of the Hive's first commit, which the joining device pins.
- `founder`: the founder key's SSH fingerprint (`SHA256:` and 43 base64 characters).
- `public_copy` (optional): the https URL of the reviewed public copy, a separate
  repository with `PUBLISHED.md` checked with `check-public`. It is the Hive's only
  public face.

## Joining

Joining through Hive Hub saves a reversible local subscription and nothing else. The
next step happens in your own Brainstem: its Hive agent `join`, given exactly
`address` and `id` = `root`, proposes first. After your yes in a later turn it copies
the shared copy, checks every commit from the root, pins the root and the Hive id,
shows the founder key fingerprint and files one SSH-signed request file
(`request: rapp-hive`) at `requests/<name>/<device>.md`. Members admit you by moving
that file into `members/<name>/keys/`. New Hives start at 2 approvals.

Hive Hub never reaches the address, writes into a Hive, runs the Hive agent or its
checker, or holds a key, so it cannot tell a private shared copy from a missing one.
`rapp-hive/1` remains the Private Hive profile in force; `rapp-hive/2` is frozen as a
research record.
"""


def documents() -> dict[str, dict[str, Any]]:
    conformance = ConformanceContract.create(
        version="0-experimental",
        requirements=[
            ConformanceRequirement(
                "brainstem-join",
                "Joining happens in the person's own Brainstem: its Hive agent join, given "
                "exactly the address pin and id = the root pin, copies the shared copy, checks "
                "every commit from that root and writes one SSH-signed request file (request: "
                "rapp-hive) at requests/<name>/<device>.md. Members admit it by moving it into "
                "members/<name>/keys/; new Hives start at 2 approvals.",
            ),
            ConformanceRequirement(
                "checker",
                f"{CHECKER_COMMAND} passes: every commit after the pinned root has one parent "
                "and is signed by a key that its parent lists under members/<name>/keys/, "
                f"within the rules. Checker: {CHECKER_PATH} at {AT_COMMIT}, "
                f"SHA-256 {CHECKER_SHA256}.",
            ),
            ConformanceRequirement(
                "convention",
                f"The Hive follows {CONVENTION_SPEC_PATH} at {AT_COMMIT}, "
                f"SHA-256 {CONVENTION_SPEC_SHA256}: a git repository of markdown files with "
                "HIVE.md, members/<name>/keys/<device>.md, requests/, shared/ and former/.",
            ),
            ConformanceRequirement(
                "dial-pins",
                f"The record's learning bundle carries {PINS_ARTIFACT} with exactly address "
                "(a credential-free ssh, https or git URL, never a local path), hive (32 "
                "lowercase hex), root (the 40-hex first commit) and founder (SHA256:<43 "
                "base64>), plus an optional https public_copy; the record's URLs are exactly "
                "its URL-valued pins.",
            ),
            ConformanceRequirement(
                "hive-hub-inert",
                "Hive Hub only validates the pins and hands them to the person's Brainstem. It "
                "never reaches the address, writes into a Hive, runs the Hive agent or its "
                "checker, or holds a key, so a private shared copy and a missing one look the "
                "same.",
            ),
            ConformanceRequirement(
                "pinned-identity",
                "The joining Brainstem pins the root commit and the Hive id and shows the "
                "founder key fingerprint. The root fixes both; if either differs from its dial "
                "pin, the record is wrong and the person stops.",
            ),
            ConformanceRequirement(
                "public-copy",
                "A named public_copy is a separate reviewed repository with PUBLISHED.md, "
                "checked with check-public; it is the Hive's only public face.",
            ),
        ],
    )
    declaration = ProtocolDeclaration.create(
        name=HIVE_MD_NAME,
        protocol_version=HIVE_MD_VERSION,
        media_type="text/markdown",
        capabilities=["discover", "join-request", "public-copy", "verify"],
        conformance_address=conformance.address,
    )
    (adapter_contract,) = HIVE_MD_DECLARATION.learning_bundle.documents
    bundle = LearningBundle.create(
        protocol_fingerprint=declaration.fingerprint,
        bundle_version=f"{HIVE_MD_VERSION}-{CONVENTION_COMMIT[:7]}",
        summary=(
            "Inert learning for the experimental hive-md folder-Hive convention and this "
            f"Hive's dial pins ({PINS_ARTIFACT}); nothing in it runs."
        ),
        conformance_contract=conformance,
        artifacts=[
            LearningArtifact.create(
                name="hive-md/adapter-contract.json",
                media_type="application/json",
                content=adapter_contract.content,
            ),
            LearningArtifact.create(
                name=PINS_ARTIFACT,
                media_type="application/json",
                content=CONTOSO_PINS.artifact_text(),
            ),
            LearningArtifact.create(
                name="hive-md/folder-hive.md",
                media_type="text/markdown",
                content=FOLDER_HIVE_TEXT,
            ),
        ],
    )
    adapter = AdapterRegistration.create(
        protocol_fingerprint=declaration.fingerprint,
        name=HIVE_MD_DECLARATION.adapter_id,
        adapter_version=HIVE_MD_VERSION,
        locator=(
            f"urn:hivehub:adapter:{HIVE_MD_DECLARATION.adapter_id}"
            f":sha256:{HIVE_MD_FINGERPRINT.contract_sha256}"
        ),
        conformance_address=conformance.address,
        operations=["handoff", "validate"],
        effect_kinds=["other"],
    )
    record = DialRecord.create(
        name="Contoso Onboarding (model Hive)",
        description=(
            "Synthetic folder Hive (hive-md, experimental) from kody-w/rapp-model-hive at "
            f"commit {CONVENTION_COMMIT[:7]}, founded by Avery with a public test key. It is a "
            "published snapshot with no live shared copy: its address uses the reserved "
            ".invalid domain and resolves nowhere. Read its reviewed public copy instead."
        ),
        visibility="public",
        protocol_fingerprint=declaration.fingerprint,
        learning_bundle_address=bundle.address,
        adapter_registration_address=adapter.address,
        urls=CONTOSO_PINS.urls,
    )
    validate_record_contracts(record, declaration, bundle, adapter)
    pins_artifact = next(item for item in bundle.artifacts if item.name == PINS_ARTIFACT)
    pins = HiveMdDialPinAdapter().validate_artifact(pins_artifact.content)
    handoff = HiveMdDialPinAdapter().handoff(pins)
    adapter_plan = AdapterPlan.create(
        adapter_registration_address=adapter.address,
        record_id=record.id,
        effects=[
            AdapterEffect.create(
                effect_id="brainstem-hive-join",
                kind="other",
                description=handoff.description(),
                locator=pins.address,
            )
        ],
    )
    human_card, ai_card = (
        AIJoinCard.create(
            principal=principal,
            locator=record.id,
            expected_record_id=record.id,
            expected_protocol_fingerprint=declaration.fingerprint,
            adapter_plan=adapter_plan,
            issued_at=FIXED_TIME,
        )
        for principal in (
            Principal.create(kind="human", identifier="person:example"),
            Principal.create(kind="ai", identifier="agent:example"),
        )
    )
    return {
        "conformance-contract.json": conformance.to_dict(),
        "protocol-declaration.json": declaration.to_dict(),
        "protocol-fingerprint.json": ProtocolFingerprint.from_declaration(declaration).to_dict(),
        "learning-bundle.json": bundle.to_dict(),
        "adapter-registration.json": adapter.to_dict(),
        "public-dial-record.json": record.to_dict(),
        "human-join-card.json": human_card.to_dict(),
        "ai-join-card.json": ai_card.to_dict(),
        "manifest.json": {
            "adapter_registration_address": adapter.address,
            "chant": derive_chant(record.dial_id),
            "dial_pins": pins.to_document(),
            "dial_record_id": record.id,
            "learning_bundle_address": bundle.address,
            "live_shared_copy": False,
            "protocol_fingerprint": declaration.fingerprint,
        },
    }


def build(target: Path = TARGET) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, value in documents().items():
        (target / name).write_bytes(canonical_bytes(value) + b"\n")


if __name__ == "__main__":
    build()
