from __future__ import annotations

import hashlib
import re
from typing import Any

from .errors import LimitError, ValidationError

CHANT_PROTOCOL = "hive-hub-chant/1"
CHANT_ADDRESS_BITS = 49
CHANT_VOCABULARY_SHA256 = (
    "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36"
)
CHANT_VOCABULARY_PROVENANCE = (
    "kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae"
)
CHANT_VOCABULARY_SOURCE = (
    "https://github.com/kody-w/rappid/blob/"
    "c988d7975dadb6a8f055183cdbc4cbb17adfe2ae/SPEC.md#11-the-dogg-layer"
)

# Byte-exact vocabulary owned by the RAPPID source above and reused here as
# protocol data. The Hive Hub derivation does not parse or require a RAPPID.
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
CHANT_VOCABULARY = CHANT_WORDS
CHANT_WORD_SET = frozenset(CHANT_WORDS)
DIAL_RECORD_ID_PATTERN = r"^dial:sha256:[0-9a-f]{64}$"
CHANT_PATTERN = (
    r"^(?:" + "|".join(CHANT_WORDS) + r")"
    + (r"-(?:" + "|".join(CHANT_WORDS) + r")") * 6
    + r"$"
)
_DIAL_RECORD_ID_RE = re.compile(DIAL_RECORD_ID_PATTERN, re.ASCII)
_CHANT_RE = re.compile(CHANT_PATTERN, re.ASCII)

assert len(CHANT_WORDS) == 128
assert len(CHANT_WORD_SET) == 128
assert (
    hashlib.sha256("\n".join(CHANT_WORDS).encode("utf-8")).hexdigest()
    == CHANT_VOCABULARY_SHA256
)


def validate_dial_record_id(value: Any) -> str:
    if not isinstance(value, str) or _DIAL_RECORD_ID_RE.fullmatch(value) is None:
        raise ValidationError(
            "dial record id must be a full canonical SHA-256 Dial Record ID"
        )
    return value


def normalize_chant(value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError("chant must be a string")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError("chant must contain valid Unicode") from exc
    if len(encoded) > 512:
        raise LimitError("chant exceeds the configured byte limit")
    normalized = value.casefold().strip()
    if "-" in normalized:
        if any(character.isspace() for character in normalized):
            raise ValidationError(
                "chant must use spaces or canonical hyphens, not both"
            )
        words = normalized.split("-")
    else:
        words = normalized.split()
    chant = "-".join(words)
    if len(words) != 7 or _CHANT_RE.fullmatch(chant) is None:
        raise ValidationError(
            "chant must be exactly seven words from the frozen vocabulary"
        )
    return chant


def derive_chant(dial_record_id: Any) -> str:
    canonical_id = validate_dial_record_id(dial_record_id)
    digest = hashlib.sha256(canonical_id.encode("utf-8")).digest()
    return "-".join(CHANT_WORDS[byte % 128] for byte in digest[:7])


def verify_chant(dial_record_id: Any, chant: Any) -> str:
    canonical_id = validate_dial_record_id(dial_record_id)
    canonical_chant = normalize_chant(chant)
    if canonical_chant != derive_chant(canonical_id):
        raise ValidationError("chant does not match the full Dial Record ID")
    return canonical_chant


def chant_contract() -> dict[str, Any]:
    return {
        "protocol": CHANT_PROTOCOL,
        "algorithm": "sha256(utf8(full-canonical-dial-record-id))[0:7] mod 128",
        "address_bits": CHANT_ADDRESS_BITS,
        "separator": "-",
        "human_input": "case-insensitive words separated by spaces or hyphens",
        "vocabulary_sha256": CHANT_VOCABULARY_SHA256,
        "vocabulary_provenance": CHANT_VOCABULARY_PROVENANCE,
        "vocabulary_source": CHANT_VOCABULARY_SOURCE,
        "candidate_locator_only": True,
        "full_dial_id_verification_required": True,
        "requires_rapp_identity": False,
        "requires_rapp_runtime": False,
    }
