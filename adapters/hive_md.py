"""Experimental folder-Hive (``hive-md``) dial pins: offline validation and a Brainstem hand-off.

A folder Hive is a git repository of markdown files in which every change is an SSH-signed
commit (``HIVE-MD.md`` in ``kody-w/rapp-model-hive``, branch ``experimental/hive-md``). A dial
record carries its pins: the shared-copy ``address``, the ``hive`` id, the pinned first commit
(``root``), the ``founder`` key fingerprint and an optional ``public_copy``.

This adapter only checks those pins and describes the next step, which happens in the person's
own Brainstem: its Hive agent joins with exactly these pins and writes one signed request file.
It never reaches the address, writes into a Hive, runs the Hive agent or its checker, or holds
a key. It is experimental (frontier canary) and is not part of ``build_default_registry()``.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import parse_qsl, urlsplit

from .contracts import (
    AdapterDeclaration,
    AdapterRefusal,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    canonical_json,
    contract_document,
    require,
)

HIVE_MD_PROTOCOL = "hive-md/0"
HIVE_MD_NAME = "hive-md"
HIVE_MD_VERSION = "0"
HIVE_MD_STATUS = "experimental"

CONVENTION_REPOSITORY = "https://github.com/kody-w/rapp-model-hive"
CONVENTION_BRANCH = "experimental/hive-md"
CONVENTION_COMMIT = "2bd7c95152ede719b6418b80e2bdc2cd457bf711"
CONVENTION_SPEC_PATH = "HIVE-MD.md"
CONVENTION_SPEC_SHA256 = "f3186e0d88cc36e18582171fff4ed9a68feddc4ae316f66fb8acc2982892fd96"
CHECKER_PATH = "agents/hive_agent.py"
CHECKER_SHA256 = "e9a2d7243da31fd2388f140bb8138c3d8d2db428ad09075530eb049a0355e8dd"
CHECKER_COMMAND = "python agents/hive_agent.py check <hive-folder> --root <root>"

PINS_KIND = "hive-md-dial-pins"
PINS_SCHEMA_VERSION = 1
PINS_ARTIFACT = "hive-md/dial-pins.json"
ADDRESS_SCHEMES = ("git", "https", "ssh")
PUBLIC_COPY_SCHEMES = ("https",)
MAX_URL_BYTES = 2048
MAX_PINS_BYTES = 8192

_REQUIRED_KEYS = frozenset({"kind", "schema_version", "address", "hive", "root", "founder"})
_OPTIONAL_KEYS = frozenset({"public_copy"})
_HIVE_ID_RE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/]{43}\Z", re.ASCII)
_CONTROL_OR_SPACE_RE = re.compile(r"[\x00-\x20\x7f]", re.ASCII)
_URL_CHARACTERS_RE = re.compile(r"[A-Za-z0-9._~:/@!$&'()*+,;=\[\]-]+\Z", re.ASCII)
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_NETLOC_RE = re.compile(
    rf"(?P<host>{_LABEL}(?:\.{_LABEL})*)(?::(?P<port>[1-9][0-9]{{0,4}}))?\Z",
    re.ASCII,
)
_DRIVE_RE = re.compile(r"[A-Za-z]:[\\/]", re.ASCII)
_SENSITIVE_QUERY_RE = re.compile(
    r"(?:^|[-_.])(access[-_]?key|api[-_]?key|auth|authorization|credential|key|pass|password|"
    r"private[-_]?key|secret|sig|signature|token)(?:$|[-_.])",
    re.IGNORECASE,
)

_HIVE_MD_CONTRACT = {
    "schema": HIVE_MD_PROTOCOL,
    "status": HIVE_MD_STATUS,
    "convention": {
        "repository": CONVENTION_REPOSITORY,
        "branch": CONVENTION_BRANCH,
        "commit": CONVENTION_COMMIT,
        "spec": {"path": CONVENTION_SPEC_PATH, "sha256": CONVENTION_SPEC_SHA256},
        "checker": {"path": CHECKER_PATH, "sha256": CHECKER_SHA256, "command": CHECKER_COMMAND},
    },
    "pins": {
        "artifact": PINS_ARTIFACT,
        "kind": PINS_KIND,
        "required": ["address", "founder", "hive", "root"],
        "optional": ["public_copy"],
        "address_schemes": list(ADDRESS_SCHEMES),
        "public_copy_schemes": list(PUBLIC_COPY_SCHEMES),
        "local_paths": False,
        "credentials": False,
    },
    "handoff": {
        "performed_by": "person-brainstem",
        "hive_agent_action": "join",
        "arguments": {"address": "address", "id": "root"},
        "writes": "one SSH-signed request file (request: rapp-hive)",
    },
    "network": False,
    "hive_writes": False,
    "executes": False,
}
HIVE_MD_FINGERPRINT, HIVE_MD_LEARNING = contract_document(
    HIVE_MD_PROTOCOL,
    _HIVE_MD_CONTRACT,
    source="embedded:hive-hub/hive-md/0",
)
HIVE_MD_DECLARATION = AdapterDeclaration(
    adapter_id="hive-md-dial-pins",
    fingerprint=HIVE_MD_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "pin-validation",
            RequirementLevel.REQUIRED,
            "The address, Hive id, root commit and founder fingerprint are checked offline.",
        ),
        CapabilityRequirement(
            "brainstem-hive-agent",
            RequirementLevel.REQUIRED,
            "Joining happens in the person's own Brainstem; its Hive agent writes the request.",
        ),
        CapabilityRequirement(
            "network-access",
            RequirementLevel.FORBIDDEN,
            "Nothing is fetched or probed, so a private shared copy and a missing one look alike.",
        ),
        CapabilityRequirement(
            "hive-write",
            RequirementLevel.FORBIDDEN,
            "Hive Hub never writes into a Hive.",
        ),
        CapabilityRequirement(
            "hive-agent-execution",
            RequirementLevel.FORBIDDEN,
            "Hive Hub never runs the Hive agent or its checker.",
        ),
        CapabilityRequirement(
            "credential-broker",
            RequirementLevel.FORBIDDEN,
            "No key, token or password is held, created or passed on.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "No remote operation of any kind is performed.",
        ),
    ),
    private_access_modes=(PrivateAccessMode.PUBLIC, PrivateAccessMode.ACL_ONLY),
    learning_bundle=HIVE_MD_LEARNING,
    conformance=ConformanceContract(
        profile="hive-md-dial-pins-conformance/0",
        fixtures=("adapters/fixtures/hive_md_vectors.json",),
        assertions=(
            "valid-pins-accepted",
            "malformed-root-refused",
            "malformed-hive-refused",
            "malformed-founder-refused",
            "local-path-address-refused",
            "url-credentials-refused",
            "handoff-carries-exact-pins",
            "no-network-no-writes-no-execution",
        ),
    ),
    authority_model=(
        "Signed commits decide membership, judged from the pinned root by the person's own "
        "Brainstem; Hive Hub and this adapter decide nothing."
    ),
)


def _refuse(code: str, message: str) -> NoReturn:
    raise AdapterRefusal(code, message)


def _looks_local(value: str) -> bool:
    return (
        value in {".", "..", "~"}
        or value.startswith(("/", "\\", "~/", "~\\", "./", "../", ".\\", "..\\"))
        or value[:5].lower() == "file:"
        or _DRIVE_RE.match(value) is not None
    )


def _url(value: object, *, schemes: tuple[str, ...], code: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        _refuse(code, f"The {label} must be a non-empty URL string.")
    require(
        not _looks_local(value),
        "local-path-address" if label == "address" else code,
        f"The {label} must be a network URL; a local path names one device's folder.",
    )
    require(
        value.isascii()
        and len(value) <= MAX_URL_BYTES
        and _CONTROL_OR_SPACE_RE.search(value) is None
        and not value.startswith("-")
        and "::" not in value,
        code,
        f"The {label} must be a bounded ASCII URL without spaces or helper syntax.",
    )
    require(
        any(value.startswith(scheme + "://") for scheme in schemes),
        code,
        f"The {label} must use one of these URL schemes: {', '.join(schemes)}.",
    )
    try:
        parsed = urlsplit(value)
    except ValueError:
        _refuse(code, f"The {label} is not a valid URL.")
    require(
        "@" not in parsed.netloc,
        "url-credentials",
        f"The {label} must not carry a user name, password or token.",
    )
    require(
        not any(
            _SENSITIVE_QUERY_RE.search(name)
            for name, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ),
        "url-credentials",
        f"The {label} must not carry credentials in its query.",
    )
    require(
        "?" not in value and "#" not in value and _URL_CHARACTERS_RE.fullmatch(value) is not None,
        code,
        f"The {label} must have no query, fragment or percent-encoding.",
    )
    authority = _NETLOC_RE.fullmatch(parsed.netloc)
    require(
        authority is not None
        and len(authority["host"]) <= 253
        and (authority["port"] is None or int(authority["port"]) <= 65535),
        code,
        f"The {label} must name a lowercase host name and an optional port.",
    )
    segments = parsed.path.split("/")
    require(
        parsed.path.startswith("/")
        and len(segments) > 1
        and all(segment not in {"", ".", ".."} for segment in segments[1:]),
        code,
        f"The {label} must name a path without empty, '.' or '..' segments.",
    )
    return value


def validate_hive_address(value: object) -> str:
    """A shared-copy git URL (ssh, https or git): no local path, credentials or query."""
    return _url(value, schemes=ADDRESS_SCHEMES, code="invalid-hive-address", label="address")


def validate_public_copy(value: object) -> str:
    """A credential-free https URL of the reviewed public copy."""
    return _url(
        value,
        schemes=PUBLIC_COPY_SCHEMES,
        code="invalid-public-copy",
        label="public copy",
    )


def validate_hive_id(value: object) -> str:
    """The ``hive:`` id the Hive agent writes into the first commit's HIVE.md."""
    if not isinstance(value, str) or _HIVE_ID_RE.fullmatch(value) is None:
        _refuse("invalid-hive-id", "The Hive id must be 32 lowercase hexadecimal characters.")
    return value


def validate_root_commit(value: object) -> str:
    """The full id of the Hive's first commit, which the joining device pins."""
    if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None or value == "0" * 40:
        _refuse(
            "invalid-root-commit",
            "The root must be one full 40-character lowercase hexadecimal commit id.",
        )
    return value


def validate_founder_fingerprint(value: object) -> str:
    """The founder key's canonical SSH ``SHA256:`` fingerprint."""
    if not isinstance(value, str) or _FINGERPRINT_RE.fullmatch(value) is None:
        _refuse(
            "invalid-founder-fingerprint",
            "The founder must be an SSH SHA256:<43 base64 characters> key fingerprint.",
        )
    body = value.removeprefix("SHA256:")
    try:
        digest = base64.b64decode(body + "=", validate=True)
    except (binascii.Error, ValueError):
        _refuse("invalid-founder-fingerprint", "The founder fingerprint is not valid base64.")
    require(
        len(digest) == 32 and base64.b64encode(digest).decode("ascii").rstrip("=") == body,
        "invalid-founder-fingerprint",
        "The founder fingerprint must encode exactly one canonical SHA-256 digest.",
    )
    return value


@dataclass(frozen=True)
class HiveMdDialPins:
    """The exact pins a dial record gives a folder Hive; construction validates every field."""

    address: str
    hive: str
    root: str
    founder: str
    public_copy: str | None = None

    def __post_init__(self) -> None:
        validate_hive_address(self.address)
        validate_hive_id(self.hive)
        validate_root_commit(self.root)
        validate_founder_fingerprint(self.founder)
        if self.public_copy is not None:
            validate_public_copy(self.public_copy)

    @property
    def urls(self) -> tuple[str, ...]:
        """The URL-valued pins, sorted, as a Dial Record lists them."""
        values = {self.address}
        if self.public_copy is not None:
            values.add(self.public_copy)
        return tuple(sorted(values))

    def to_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "kind": PINS_KIND,
            "schema_version": PINS_SCHEMA_VERSION,
            "address": self.address,
            "hive": self.hive,
            "root": self.root,
            "founder": self.founder,
        }
        if self.public_copy is not None:
            document["public_copy"] = self.public_copy
        return document

    def artifact_text(self) -> str:
        """The exact inert learning-artifact text: canonical JSON and one line feed."""
        return canonical_json(self.to_document()).decode("utf-8") + "\n"


def parse_dial_pins(value: object) -> HiveMdDialPins:
    """Validate a closed dial-pins document without touching the network or the disk."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        _refuse("invalid-dial-pins", "Dial pins must be a JSON object.")
    keys = set(value)
    require(
        _REQUIRED_KEYS <= keys <= _REQUIRED_KEYS | _OPTIONAL_KEYS,
        "invalid-dial-pins",
        "Dial pins hold exactly kind, schema_version, address, hive, root, founder and an "
        "optional public_copy.",
    )
    require(
        value["kind"] == PINS_KIND
        and type(value["schema_version"]) is int
        and value["schema_version"] == PINS_SCHEMA_VERSION,
        "invalid-dial-pins",
        "Dial pins must declare kind hive-md-dial-pins and schema_version 1.",
    )
    require(
        all(type(value[key]) is str for key in keys - {"schema_version"}),
        "invalid-dial-pins",
        "Every dial pin must be a string.",
    )
    return HiveMdDialPins(
        address=value["address"],
        hive=value["hive"],
        root=value["root"],
        founder=value["founder"],
        public_copy=value.get("public_copy"),
    )


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in result, "invalid-dial-pins", "Dial pins must not repeat a key.")
        result[key] = item
    return result


def _no_number(_value: str) -> NoReturn:
    _refuse("invalid-dial-pins", "Dial pins hold no numbers other than schema_version.")


def parse_dial_pins_artifact(content: object) -> HiveMdDialPins:
    """Parse the exact inert ``hive-md/dial-pins.json`` artifact text from a learning bundle."""
    if not isinstance(content, str) or len(content) > MAX_PINS_BYTES:
        _refuse("invalid-dial-pins", "The dial pins artifact must be bounded text.")
    try:
        value = json.loads(
            content,
            object_pairs_hook=_no_duplicates,
            parse_float=_no_number,
            parse_constant=_no_number,
        )
    except AdapterRefusal:
        raise
    except (ValueError, RecursionError) as error:
        raise AdapterRefusal("invalid-dial-pins", "The dial pins artifact is not JSON.") from error
    pins = parse_dial_pins(value)
    require(
        pins.artifact_text() == content,
        "invalid-dial-pins",
        "The dial pins artifact must be canonical JSON followed by one line feed.",
    )
    return pins


@dataclass(frozen=True)
class BrainstemHandoff:
    """The next step for the person's own Brainstem. Hive Hub describes it and performs none."""

    pins: HiveMdDialPins

    @property
    def call(self) -> dict[str, str]:
        """The Hive agent ``join`` inputs taken from the pins; name and device are the person's."""
        return {"action": "join", "address": self.pins.address, "id": self.pins.root}

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "hive-md-brainstem-handoff",
            "schema_version": 1,
            "performed_by": "person-brainstem",
            "hive_agent": {"path": CHECKER_PATH, "sha256": CHECKER_SHA256, "tool": "Hive"},
            "call": self.call,
            "person_supplies": ["device", "name"],
            "compare": {"founder": self.pins.founder, "hive": self.pins.hive},
            "writes": "requests/<name>/<device>.md",
            "request": "rapp-hive",
            "public_copy": self.pins.public_copy,
            "hive_hub_effects": [],
        }

    def description(self) -> str:
        """One line of plain words for an inert adapter-plan effect."""
        pins = self.pins
        text = (
            "Next step, in your own Brainstem, not Hive Hub: ask its Hive agent "
            f"({CHECKER_PATH}) to join with exactly address {pins.address} and id {pins.root} "
            "(the pinned root commit), plus your own name and device. It proposes first and acts "
            "only after your yes in a later turn: it copies the shared copy, checks every commit "
            "from that root, pins the root and the Hive id, and files one SSH-signed request "
            "file (request: rapp-hive) at requests/<name>/<device>.md. It must report Hive id "
            f"{pins.hive} and founder key {pins.founder}; if either differs, stop. Members admit "
            "you by moving that file into members/<name>/keys/. Hive Hub runs none of this and "
            "never writes into the Hive."
        )
        if pins.public_copy is not None:
            text += f" The reviewed public copy is {pins.public_copy}; check it with check-public."
        return text


class HiveMdDialPinAdapter:
    """Validates folder-Hive dial pins and hands them to the person's Brainstem; nothing else."""

    declaration = HIVE_MD_DECLARATION

    def validate(self, value: object) -> HiveMdDialPins:
        return parse_dial_pins(value)

    def validate_artifact(self, content: object) -> HiveMdDialPins:
        return parse_dial_pins_artifact(content)

    def handoff(self, pins: HiveMdDialPins) -> BrainstemHandoff:
        require(
            isinstance(pins, HiveMdDialPins),
            "invalid-dial-pins",
            "A hand-off needs validated dial pins.",
        )
        return BrainstemHandoff(pins)
