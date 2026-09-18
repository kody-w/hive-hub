"""Pure Payphone DoorRef derivation and privacy-clean dial evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    AdapterRefusal,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    contract_document,
    require,
)
from .rappid import Rappid, parse_rappid

PAYPHONE_PROTOCOL = "rapp-payphone-dial/1.0"
DOOR_REF_SCHEMA = "rapp-door-ref/1.0"
DIAL_RESULT_SCHEMA = "rapp-dial-result/1.0"
_PAYPHONE_CONTRACT = {
    "schema": PAYPHONE_PROTOCOL,
    "input": "exact-full-rappid",
    "door_ref": DOOR_REF_SCHEMA,
    "derivation": {
        "peer_id": "rapp-door- + door_id[:32]",
        "label": "rapp-dial/ + door_id[:16]",
        "raw": "https://raw.githubusercontent.com/<owner>/<repo>/main/.neighborhood/",
    },
    "outcomes": ["connected", "unreachable"],
    "unreachable_collapses": ["absent", "unauthorized", "identity-mismatch"],
    "truncated_ids_authorize": False,
    "writes": False,
}
PAYPHONE_FINGERPRINT, PAYPHONE_LEARNING = contract_document(
    PAYPHONE_PROTOCOL,
    _PAYPHONE_CONTRACT,
    source=(
        "https://github.com/kody-w/rapp-neighborhood-protocol/blob/"
        "44e0c6eb49d619932e645fb9d9b12a5fa37f71b1/PAYPHONE.md"
    ),
)
PAYPHONE_DECLARATION = AdapterDeclaration(
    adapter_id="rapp-payphone",
    fingerprint=PAYPHONE_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "full-rappid-verification",
            RequirementLevel.REQUIRED,
            "A connection is accepted only after exact full-RAPPID verification.",
        ),
        CapabilityRequirement(
            "caller-credentials",
            RequirementLevel.OPTIONAL,
            "The caller's transport may use its already-held ACL credentials.",
        ),
        CapabilityRequirement(
            "truncated-id-authority",
            RequirementLevel.FORBIDDEN,
            "Peer and label prefixes are routing locators and may collide.",
        ),
        CapabilityRequirement(
            "credential-broker",
            RequirementLevel.FORBIDDEN,
            "The Payphone holds no repository credentials or private keys.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "This adapter derives and verifies; it never opens Issues or PRs.",
        ),
    ),
    private_access_modes=(
        PrivateAccessMode.ACL_ONLY,
        PrivateAccessMode.ACL_PLUS_QR,
    ),
    learning_bundle=PAYPHONE_LEARNING,
    conformance=ConformanceContract(
        profile="rapp-payphone-dial-conformance/1.0",
        fixtures=("adapters/fixtures/payphone_vectors.json",),
        assertions=(
            "door-ref-byte-exact",
            "pure-no-io-derivation",
            "connected-unreachable-only",
            "absent-unauthorized-indistinguishable",
            "full-rappid-required",
            "truncated-collision-refused",
            "no-remote-writes",
        ),
    ),
    authority_model="Source ACL and optional second factor gate access; DoorRef is only a locator.",
)


@dataclass(frozen=True)
class WebRtcTether:
    channel: str
    peer_id: str


@dataclass(frozen=True)
class IssuesTether:
    channel: str
    repo: str
    label: str


@dataclass(frozen=True)
class PullRequestTether:
    channel: str
    repo: str
    base: str
    head_prefix: str


@dataclass(frozen=True)
class RawTether:
    channel: str
    base: str


@dataclass(frozen=True)
class Tethers:
    webrtc: WebRtcTether
    issues: IssuesTether
    pr: PullRequestTether
    raw: RawTether


@dataclass(frozen=True)
class DoorRef:
    schema: str
    rappid: str
    owner: str
    repo: str
    door_id: str
    tethers: Tethers

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _door_from_parsed(rappid: Rappid) -> DoorRef:
    repository = f"{rappid.owner}/{rappid.slug}"
    return DoorRef(
        schema=DOOR_REF_SCHEMA,
        rappid=rappid.canonical,
        owner=rappid.owner,
        repo=rappid.slug,
        door_id=rappid.tail,
        tethers=Tethers(
            webrtc=WebRtcTether(
                channel="5a-tether",
                peer_id=f"rapp-door-{rappid.tail[:32]}",
            ),
            issues=IssuesTether(
                channel="5b-issues",
                repo=repository,
                label=f"rapp-dial/{rappid.tail[:16]}",
            ),
            pr=PullRequestTether(
                channel="5b-pr",
                repo=repository,
                base="main",
                head_prefix="rapp-dial/",
            ),
            raw=RawTether(
                channel="5a-raw",
                base=(
                    "https://raw.githubusercontent.com/"
                    f"{repository}/main/.neighborhood/"
                ),
            ),
        ),
    )


def door_from_rappid(rappid: str) -> DoorRef:
    """Pure exact-RAPPID to DoorRef derivation with no file/network/clock access."""

    return _door_from_parsed(parse_rappid(rappid))


@dataclass(frozen=True)
class DoorObservation:
    access: AccessOutcome
    presented_rappid: str | None
    peer_id: str | None = None
    label: str | None = None
    qr_verified: bool | None = None


@dataclass(frozen=True)
class DialResult:
    schema: str
    rappid: str
    outcome: str


DoorProbe = Callable[[DoorRef], DoorObservation]


class PayphoneAdapter:
    declaration = PAYPHONE_DECLARATION

    def door_from_rappid(self, rappid: str) -> DoorRef:
        return door_from_rappid(rappid)

    def evaluate(
        self,
        rappid: str,
        observation: DoorObservation,
        *,
        access_mode: PrivateAccessMode = PrivateAccessMode.ACL_ONLY,
    ) -> DialResult:
        require(
            access_mode in {PrivateAccessMode.ACL_ONLY, PrivateAccessMode.ACL_PLUS_QR},
            "invalid-payphone-access-mode",
            "Payphone supports only ACL or ACL plus QR second factor.",
        )
        expected = door_from_rappid(rappid)
        connected = observation.access is AccessOutcome.REACHABLE
        if connected:
            try:
                presented = (
                    parse_rappid(observation.presented_rappid).canonical
                    if observation.presented_rappid is not None
                    else None
                )
            except AdapterRefusal:
                presented = None
            connected = presented == expected.rappid
        if connected and observation.peer_id is not None:
            connected = observation.peer_id == expected.tethers.webrtc.peer_id
        if connected and observation.label is not None:
            connected = observation.label == expected.tethers.issues.label
        if connected and access_mode is PrivateAccessMode.ACL_PLUS_QR:
            connected = observation.qr_verified is True
        return DialResult(
            schema=DIAL_RESULT_SCHEMA,
            rappid=expected.rappid,
            outcome="connected" if connected else "unreachable",
        )

    def dial(
        self,
        rappid: str,
        probe: DoorProbe,
        *,
        access_mode: PrivateAccessMode = PrivateAccessMode.ACL_ONLY,
    ) -> DialResult:
        door = door_from_rappid(rappid)
        try:
            observation = probe(door)
        except (AdapterRefusal, OSError, TimeoutError):
            observation = DoorObservation(
                access=AccessOutcome.UNREACHABLE,
                presented_rappid=None,
            )
        return self.evaluate(rappid, observation, access_mode=access_mode)

    def resolve_truncated(
        self,
        reference: str,
        candidate_rappids: Iterable[str],
        *,
        full_rappid: str | None,
    ) -> DoorRef:
        candidates: dict[str, DoorRef] = {}
        for candidate_rappid in candidate_rappids:
            candidate = door_from_rappid(candidate_rappid)
            if reference in {
                candidate.tethers.webrtc.peer_id,
                candidate.tethers.issues.label,
            }:
                candidates[candidate.rappid] = candidate
        if full_rappid is None:
            if len(candidates) > 1:
                raise AdapterRefusal(
                    "payphone-truncated-collision",
                    "The truncated Payphone locator has multiple full-RAPPID candidates.",
                )
            raise AdapterRefusal(
                "payphone-full-rappid-required",
                "A truncated Payphone locator cannot authorize without a full RAPPID.",
            )
        canonical = parse_rappid(full_rappid).canonical
        require(
            canonical in candidates,
            "payphone-rappid-mismatch",
            "No truncated locator candidate matches the complete requested RAPPID.",
        )
        return candidates[canonical]
