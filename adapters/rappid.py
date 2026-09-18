"""Exact RAPPID parser and frozen seven-word summon chant adapter."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .contracts import (
    AdapterDeclaration,
    AdapterRefusal,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    contract_document,
    require,
)

RAPPID_RE = re.compile(
    r"rappid:@(?P<owner>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*):"
    r"(?P<tail>[0-9a-f]{64})\Z",
    re.ASCII,
)
CHANT_WORD_RE = re.compile(r"[a-z]{1,32}\Z", re.ASCII)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

# Frozen by kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae.
CHANT_WORDS = (
    "ember",
    "hollow",
    "quartz",
    "tidal",
    "vessel",
    "marrow",
    "lantern",
    "thicket",
    "basalt",
    "cinder",
    "willow",
    "fathom",
    "granite",
    "sable",
    "harbor",
    "kestrel",
    "amber",
    "furrow",
    "lichen",
    "brindle",
    "aspen",
    "bramble",
    "cobalt",
    "drift",
    "eddy",
    "fenlark",
    "gully",
    "heron",
    "inkcap",
    "juniper",
    "knoll",
    "loam",
    "mica",
    "nettle",
    "osprey",
    "petrel",
    "quill",
    "rushes",
    "shale",
    "tarn",
    "umber",
    "vale",
    "wren",
    "yarrow",
    "zephyr",
    "alder",
    "briar",
    "cairn",
    "dune",
    "elm",
    "flint",
    "gorse",
    "hazel",
    "iris",
    "jetty",
    "kelp",
    "larch",
    "moss",
    "north",
    "otter",
    "pine",
    "quarry",
    "reed",
    "spruce",
    "thorn",
    "upland",
    "vetch",
    "wharf",
    "yew",
    "arbor",
    "birch",
    "cedar",
    "delta",
    "ester",
    "fjord",
    "glade",
    "heath",
    "islet",
    "jasper",
    "karst",
    "ledge",
    "mesa",
    "nadir",
    "oxbow",
    "prairie",
    "quiver",
    "ridge",
    "steppe",
    "trench",
    "ursa",
    "verge",
    "wold",
    "xenia",
    "yonder",
    "zenith",
    "anvil",
    "bluff",
    "crag",
    "dell",
    "ebb",
    "ford",
    "grove",
    "hearth",
    "ivy",
    "jade",
    "kiln",
    "lark",
    "mire",
    "nook",
    "orchid",
    "pond",
    "quay",
    "rill",
    "sedge",
    "tor",
    "usher",
    "vine",
    "weir",
    "xylem",
    "yield",
    "zeal",
    "atlas",
    "beacon",
    "cove",
    "dusk",
    "frost",
    "gale",
    "haven",
)
RAPPID_VOCABULARY_SHA256 = (
    "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36"
)
assert len(CHANT_WORDS) == 128
assert len(set(CHANT_WORDS)) == 128
assert (
    hashlib.sha256("\n".join(CHANT_WORDS).encode("utf-8")).hexdigest()
    == RAPPID_VOCABULARY_SHA256
)

RAPPID_CHANT_PROTOCOL = "rappidex/1-summon-chant"
_RAPPID_CHANT_CONTRACT = {
    "schema": RAPPID_CHANT_PROTOCOL,
    "rappid_grammar": "rappid:@lower-owner/lower-slug:64-lower-hex",
    "owner_max": 39,
    "slug_max": 100,
    "algorithm": "sha256(utf8(canonical_rappid))[0..6] mod 128",
    "separator": "-",
    "human_input": "case-insensitive words separated by spaces or hyphens",
    "vocabulary_sha256": RAPPID_VOCABULARY_SHA256,
    "address_bits": 49,
    "authority": False,
    "collision_policy": "retain-all-full-rappid-candidates",
}
RAPPID_CHANT_FINGERPRINT, RAPPID_CHANT_LEARNING = contract_document(
    RAPPID_CHANT_PROTOCOL,
    _RAPPID_CHANT_CONTRACT,
    source=(
        "https://github.com/kody-w/rappid/blob/"
        "c988d7975dadb6a8f055183cdbc4cbb17adfe2ae/SPEC.md#11-the-dogg-layer"
    ),
)
RAPPID_CHANT_DECLARATION = AdapterDeclaration(
    adapter_id="rappid-seven-word-chant",
    fingerprint=RAPPID_CHANT_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "sha256",
            RequirementLevel.REQUIRED,
            "The exact summon address is derived from SHA-256.",
        ),
        CapabilityRequirement(
            "identity-authority",
            RequirementLevel.FORBIDDEN,
            "A 49-bit chant is a locator, never identity or authority.",
        ),
        CapabilityRequirement(
            "first-candidate-wins",
            RequirementLevel.FORBIDDEN,
            "All full-RAPPID collision candidates must be retained.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "Chant derivation and resolution are pure local operations.",
        ),
    ),
    private_access_modes=(PrivateAccessMode.PUBLIC,),
    learning_bundle=RAPPID_CHANT_LEARNING,
    conformance=ConformanceContract(
        profile="rappidex-chant-conformance/1.0",
        fixtures=("adapters/fixtures/rappid_vectors.json",),
        assertions=(
            "vocabulary-byte-exact",
            "upstream-vectors-byte-exact",
            "human-case-space-normalization",
            "strict-canonical-rappid",
            "collision-candidates-retained",
            "full-rappid-disambiguation",
        ),
    ),
    authority_model="Chants locate candidates; the complete RAPPID and pinned bytes verify them.",
)


@dataclass(frozen=True)
class Rappid:
    owner: str
    slug: str
    tail: str

    @property
    def canonical(self) -> str:
        return f"rappid:@{self.owner}/{self.slug}:{self.tail}"


def parse_rappid(value: str) -> Rappid:
    require(
        type(value) is str,
        "invalid-rappid",
        "RAPPID must be a string.",
    )
    match = RAPPID_RE.fullmatch(value)
    require(
        match is not None,
        "invalid-rappid",
        "RAPPID does not match the exact canonical grammar.",
    )
    assert match is not None
    owner = match.group("owner")
    slug = match.group("slug")
    require(
        len(owner) <= 39 and len(slug) <= 100,
        "invalid-rappid",
        "RAPPID owner or slug exceeds the canonical bound.",
    )
    return Rappid(owner, slug, match.group("tail"))


def normalize_chant(value: str) -> str:
    require(
        type(value) is str and bool(value.strip()),
        "invalid-chant",
        "A summon chant must be a non-empty string.",
    )
    normalized = value.strip().lower()
    if "-" in normalized:
        require(
            not any(character.isspace() for character in normalized),
            "invalid-chant",
            "Use either spaces or canonical hyphens between chant words.",
        )
        words = normalized.split("-")
    else:
        words = normalized.split()
    require(
        len(words) == 7
        and all(words)
        and all(CHANT_WORD_RE.fullmatch(word) is not None for word in words)
        and all(word in CHANT_WORDS for word in words),
        "invalid-chant",
        "A summon chant is exactly seven words from the frozen vocabulary.",
    )
    return "-".join(words)


class ChantDeriver(Protocol):
    def chant_for_rappid(self, rappid: str) -> str: ...


class RappidChantAdapter:
    declaration = RAPPID_CHANT_DECLARATION

    def parse_rappid(self, value: str) -> Rappid:
        return parse_rappid(value)

    def normalize(self, value: str) -> str:
        return normalize_chant(value)

    def chant_for_rappid(self, rappid: str) -> str:
        canonical = parse_rappid(rappid).canonical
        digest = hashlib.sha256(canonical.encode("utf-8")).digest()
        return "-".join(CHANT_WORDS[digest[index] % 128] for index in range(7))


@dataclass(frozen=True)
class ChantCandidate:
    rappid: str
    source: str
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        parse_rappid(self.rappid)
        require(
            bool(self.source.strip()),
            "invalid-chant-candidate",
            "A chant candidate must retain its source.",
        )
        if self.content_sha256 is not None:
            require(
                SHA256_RE.fullmatch(self.content_sha256) is not None,
                "invalid-chant-candidate",
                "Candidate content pins must be lowercase SHA-256 values.",
            )


@dataclass(frozen=True)
class ChantResolution:
    chant: str
    candidates: tuple[ChantCandidate, ...]

    @property
    def outcome(self) -> str:
        if not self.candidates:
            return "not-found"
        if len(self.candidates) == 1:
            return "unique"
        return "collision"


class ChantCandidateResolver:
    """Collision-preserving lookup over caller-supplied full candidates."""

    def __init__(self, deriver: ChantDeriver | None = None) -> None:
        self._deriver = deriver or RappidChantAdapter()

    def resolve(
        self,
        spoken_chant: str,
        candidates: Iterable[ChantCandidate],
    ) -> ChantResolution:
        chant = normalize_chant(spoken_chant)
        matched = {
            candidate
            for candidate in candidates
            if self._deriver.chant_for_rappid(candidate.rappid) == chant
        }
        return ChantResolution(
            chant=chant,
            candidates=tuple(
                sorted(
                    matched,
                    key=lambda candidate: (
                        candidate.rappid,
                        candidate.source,
                        candidate.content_sha256 or "",
                    ),
                )
            ),
        )

    def select(
        self,
        resolution: ChantResolution,
        *,
        full_rappid: str | None,
        content_sha256: str | None = None,
    ) -> ChantCandidate:
        if full_rappid is None:
            if len(resolution.candidates) > 1:
                raise AdapterRefusal(
                    "chant-collision",
                    "The chant has multiple candidates; the full RAPPID is required.",
                )
            require(
                len(resolution.candidates) == 1,
                "chant-not-found",
                "The chant has no candidate.",
            )
            candidate = resolution.candidates[0]
        else:
            canonical = parse_rappid(full_rappid).canonical
            matches = [
                candidate
                for candidate in resolution.candidates
                if candidate.rappid == canonical
            ]
            require(
                len(matches) == 1,
                "rappid-not-found",
                "No chant candidate carries the complete requested RAPPID.",
            )
            candidate = matches[0]
        if content_sha256 is not None:
            require(
                SHA256_RE.fullmatch(content_sha256) is not None
                and candidate.content_sha256 == content_sha256,
                "candidate-pin-mismatch",
                "The selected candidate does not match the required content pin.",
            )
        return candidate
