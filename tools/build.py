#!/usr/bin/env python3
"""Build a hub's views from its cards, with the Python standard library only.

A hub is a tree of markdown cards, one fact per file. This builder checks every card and every
starter template, then generates views/: the api/v2 JSON, a static site that needs no
JavaScript, and chants.txt. Nothing in a hub runs, and the builder writes only inside views/.

    python tools/build.py              check the hub and write views/
    python tools/build.py --check      rebuild in memory and compare with views/ byte for byte
    python tools/build.py --root DIR   build another hub folder

The same file builds every hub. Everything hub-specific lives in HUB.md, cards/ and starters/.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

API = "hub/v2"

# The frozen hive-hub-chant/1 vocabulary, byte-exact from kody-w/rappid at commit
# c988d7975dadb6a8f055183cdbc4cbb17adfe2ae. WORDS_SHA256 is the SHA-256 of the words joined by
# newlines. A chant is a locator, never authority.
WORDS = (
    "ember", "hollow", "quartz", "tidal", "vessel", "marrow", "lantern", "thicket", "basalt",
    "cinder", "willow", "fathom", "granite", "sable", "harbor", "kestrel", "amber", "furrow",
    "lichen", "brindle", "aspen", "bramble", "cobalt", "drift", "eddy", "fenlark", "gully",
    "heron", "inkcap", "juniper", "knoll", "loam", "mica", "nettle", "osprey", "petrel",
    "quill", "rushes", "shale", "tarn", "umber", "vale", "wren", "yarrow", "zephyr", "alder",
    "briar", "cairn", "dune", "elm", "flint", "gorse", "hazel", "iris", "jetty", "kelp",
    "larch", "moss", "north", "otter", "pine", "quarry", "reed", "spruce", "thorn", "upland",
    "vetch", "wharf", "yew", "arbor", "birch", "cedar", "delta", "ester", "fjord", "glade",
    "heath", "islet", "jasper", "karst", "ledge", "mesa", "nadir", "oxbow", "prairie",
    "quiver", "ridge", "steppe", "trench", "ursa", "verge", "wold", "xenia", "yonder",
    "zenith", "anvil", "bluff", "crag", "dell", "ebb", "ford", "grove", "hearth", "ivy",
    "jade", "kiln", "lark", "mire", "nook", "orchid", "pond", "quay", "rill", "sedge", "tor",
    "usher", "vine", "weir", "xylem", "yield", "zeal", "atlas", "beacon", "cove", "dusk",
    "frost", "gale", "haven",
)
WORDS_SHA256 = "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36"

KINDS = {  # kind: (folder under cards/ and in views/, heading on the site)
    "protocol": ("protocols", "Protocols"),
    "hive": ("hives", "Hives"),
    "organization": ("orgs", "Organizations"),
    "starter": ("starters", "Starters"),
}
FOLDERS = {folder: kind for kind, (folder, _) in KINDS.items()}
REQUIRED = {
    "protocol": ("card", "id", "name", "status", "spec", "spec_sha256"),
    "hive": ("card", "name", "protocol", "status", "channel"),
    "organization": ("card", "name", "status", "hive"),
    "starter": ("card", "name", "status", "template", "org"),
}
OPTIONAL = {
    "protocol": ("checker", "checker_sha256", "agent", "agent_sha256"),
    "hive": ("hive", "root", "founder", "public_copy", "address", "org"),
    "organization": ("starter",),
    "starter": (),
}
PAIRS = (("checker", "checker_sha256"), ("agent", "agent_sha256"))
PINS = ("hive", "root", "founder")
STATUSES = {"protocol": ("in force", "specified", "experimental", "candidate", "frozen")}
OTHER_STATUSES = ("in force", "specified", "experimental", "candidate", "planned", "frozen")
MAX_CARD_BYTES = 32 << 10
MAX_TEMPLATE_FILE_BYTES = 1 << 20
MAX_TEMPLATE_PATH = 120
MAX_URL = 2048

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PROTOCOL_ID = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*(?:/[a-z0-9]+(?:[.-][a-z0-9]+)*)*\Z")
LINE = re.compile(r"([a-z][a-z0-9_]*): (\S(?:.*\S)?)\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}\Z")
HIVE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:@/._+-]{0,127}\Z")
TEMPLATE = re.compile(r"starters/([a-z0-9]+(?:-[a-z0-9]+)*)/\Z")
URL_CHARACTERS = re.compile(r"[A-Za-z0-9._~:/@!$&'()*+,;=\[\]-]+\Z")
LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
NETLOC = re.compile(rf"(?P<host>{LABEL}(?:\.{LABEL})*)(?::(?P<port>[1-9][0-9]{{0,4}}))?\Z")
SENSITIVE_QUERY = re.compile(
    r"(?:^|[-_.])(access[-_]?key|api[-_]?key|auth|authorization|credential|key|pass|password|"
    r"private[-_]?key|secret|sig|signature|token)(?:$|[-_.])",
    re.IGNORECASE,
)
ABSOLUTE_PATH = re.compile(
    r"(?<![\w.~/-])/(?:Users|home|root|var|tmp|private|etc|opt|srv|mnt|media|Volumes|usr)/"
    r"|(?<![A-Za-z0-9])[A-Za-z]:\\|(?<![A-Za-z0-9/])[A-Za-z]:/(?!/)"
    r"|(?<![\w~])~[\\/]|file:/|(?<![\w\\])\\\\[A-Za-z0-9]",
    re.IGNORECASE,
)

# Text rules from the hive-md convention (kody-w/rapp-model-hive at 2bd7c95, HIVE-MD.md): a fixed
# list of control, bidi, invisible and private-use characters, so every system gives one verdict.
_INVISIBLE = (
    "\x7f-\x9f\ud800-\udfff\xad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f"
    "\u200b-\u200f\u2028-\u202e\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufffb"
    "\ufdd0-\ufdef\ue000-\uf8ff\U00013430-\U0001343f\U0001bca0-\U0001bca3\U0001d173-\U0001d17a"
    "\U000e0000-\U000e0fff\U000f0000-\U0010ffff"
    + "".join(chr(plane << 16 | 0xFFFE) + chr(plane << 16 | 0xFFFF) for plane in range(15))
)
HIVE_TEXT_BAD = re.compile("[\x00-\x08\x0b-\x1f" + _INVISIBLE + "]")  # tab and newline allowed
CARD_TEXT_BAD = re.compile("[\x00-\x09\x0b-\x1f" + _INVISIBLE + "]")  # newline only
_EMOJI = (
    "\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u23ff\u24c2\u25aa-\u25fe"
    "\u2600-\u27bf\u2934\u2935\u2b05-\u2b55\u3030\u303d\u3297\u3299\U0001f000-\U0001faff"
)
EMOJI_OK = re.compile(
    f"(?<=[{_EMOJI}])[\ufe0e\ufe0f]|(?<=[0-9#*])\ufe0f(?=\u20e3)"
    f"|(?:(?<=[{_EMOJI}])|(?<=[{_EMOJI}]\ufe0f))\u200d(?=[{_EMOJI}])"
)
DATAVIEWJS = re.compile(
    r"^[ \t>*+\-0-9.)]*(`{3,}|~{3,})[ \t]*dataviewjs|(?<!`)`+[ \t]*\$=", re.M | re.I)
SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}\Z")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}
INSTRUCTION_NAMES = {
    "agents.md", "claude.md", "claude.local.md", "gemini.md", "skill.md", "copilot-instructions.md"}
GITATTRIBUTES = b"* text eol=lf\n"
HIVE_KEYS = {"hive", "version", "approvals", "fields", "previous"}


class BuildError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__(f"{len(problems)} problem(s)")
        self.problems = problems


@dataclass(frozen=True)
class Card:
    kind: str
    slug: str
    path: str
    fields: dict[str, str]
    body: str
    sha256: str
    chant: str

    @property
    def ref(self) -> str:
        return f"{self.kind}/{self.slug}"

    @property
    def folder(self) -> str:
        return KINDS[self.kind][0]


def chant(digest: bytes) -> str:
    """Seven words: the first seven bytes of a card's SHA-256, each modulo 128."""
    return "-".join(WORDS[byte % 128] for byte in digest[:7])


def card_text(fields: dict[str, str], body: str) -> str:
    """The exact card file for a frontmatter and body: rebuild it to check a card's sha256."""
    head = "---\n" + "".join(f"{key}: {value}\n" for key, value in fields.items()) + "---\n"
    return head + ("\n" + body if body else "")


def _visible(text: str, bad: re.Pattern[str]) -> bool:
    return bad.search(EMOJI_OK.sub("", text)) is None


def url_problem(value: str, schemes: tuple[str, ...]) -> str | None:
    if value.startswith(("/", "\\", "~", "./", "../")) or value[:5].lower() == "file:" or (
            re.match(r"[A-Za-z]:[\\/]", value)):
        return "must be a URL, not a local path"
    if (not value.isascii() or len(value) > MAX_URL or re.search(r"[\x00-\x20\x7f]", value)
            or value.startswith("-") or "::" in value):
        return "must be a bounded ASCII URL without spaces or helper syntax"
    if not any(value.startswith(scheme + "://") for scheme in schemes):
        return "must start with " + " or ".join(f"{scheme}://" for scheme in schemes)
    try:
        parts = urlsplit(value)
    except ValueError:
        return "is not a valid URL"
    if "@" in parts.netloc:
        return "must not carry a user name, password or token (credentials in a URL)"
    if any(SENSITIVE_QUERY.search(name) for name, _ in parse_qsl(parts.query, True)):
        return "must not carry credentials in its query"
    if "?" in value or "#" in value or URL_CHARACTERS.fullmatch(value) is None:
        return "must have no query, fragment or percent-encoding"
    host = NETLOC.fullmatch(parts.netloc)
    if host is None or len(host["host"]) > 253 or (host["port"] and int(host["port"]) > 65535):
        return "must name a lowercase host and an optional port"
    segments = parts.path.split("/")
    if not parts.path.startswith("/") or any(item in ("", ".", "..") for item in segments[1:]):
        return "must name a path without empty, '.' or '..' segments"
    return None


def pinned_url_problem(value: str) -> str | None:
    problem = url_problem(value, ("https",))
    segments = urlsplit(value).path.split("/") if problem is None else []
    if problem is None and not any(COMMIT.fullmatch(part) for part in segments):
        problem = "must be pinned: include the full 40- or 64-character commit id, not a branch"
    return problem


def founder_problem(value: str) -> str | None:
    if FINGERPRINT.fullmatch(value) is None:
        return "must be an SSH key fingerprint: SHA256: and 43 base64 characters"
    body = value[len("SHA256:"):]
    try:
        digest = base64.b64decode(body + "=", validate=True)
    except (binascii.Error, ValueError):
        return "is not valid base64"
    if len(digest) != 32 or base64.b64encode(digest).decode("ascii").rstrip("=") != body:
        return "must encode exactly one SHA-256 digest in canonical base64"
    return None


def value_problem(kind: str, key: str, value: str) -> str | None:
    if key == "card":
        return None if value == kind else f"must be {kind} for a card under cards/{KINDS[kind][0]}/"
    if key == "status":
        allowed = STATUSES.get(kind, OTHER_STATUSES)
        return None if value in allowed else "must be one of: " + ", ".join(allowed)
    if key == "name":
        return None if len(value) <= 120 else "must be at most 120 characters"
    if key in ("channel", "checker"):
        return None if len(value) <= 300 else "must be at most 300 characters"
    if key in ("spec", "agent"):
        return pinned_url_problem(value)
    if key.endswith("_sha256"):
        return None if SHA256.fullmatch(value) else "must be 64 lowercase hexadecimal characters"
    if key == "root":
        if COMMIT.fullmatch(value) is None or set(value) == {"0"}:
            return "must be the full commit id: 40 or 64 lowercase hexadecimal characters"
        return None
    if key == "founder":
        return founder_problem(value)
    if key == "hive" and kind == "hive":
        return None if HIVE_ID.fullmatch(value) else "must be one token of letters, digits, :@/._+-"
    if key == "hive":
        if value == "template" or SLUG.fullmatch(value):
            return None
        return "must be a hive card slug or template"
    if key == "public_copy":
        return url_problem(value, ("https",))
    if key == "address":
        return url_problem(value, ("ssh", "https", "git"))
    if key in ("id", "protocol"):
        return None if PROTOCOL_ID.fullmatch(value) and len(value) <= 64 else "must be an id"
    if key in ("org", "starter"):
        return None if SLUG.fullmatch(value) and len(value) <= 64 else "must be a card slug"
    if key == "template":
        return None if TEMPLATE.fullmatch(value) else "must be starters/<folder>/"
    return None


def _walk(base: Path, root: Path, problems: list[str]) -> list[Path]:
    """Every plain file under base, in a fixed order. Links and special files are problems."""
    found: list[Path] = []
    folders = [base]
    while folders:
        folder = folders.pop()
        with os.scandir(folder) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                shown = path.relative_to(root).as_posix()
                if entry.is_symlink():
                    problems.append(f"{shown}: links are refused")
                elif entry.is_dir(follow_symlinks=False):
                    folders.append(path)
                elif entry.is_file(follow_symlinks=False):
                    found.append(path)
                else:
                    problems.append(f"{shown}: only plain files and folders")
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())


def _card_text_problem(text: str) -> str | None:
    if text.startswith("\ufeff"):
        return "must not start with a byte-order mark"
    if unicodedata.normalize("NFC", text) != text:
        return "must be NFC-normalized"
    if "\r" in text:
        return "must use LF line endings"
    if not text.endswith("\n") or text.endswith("\n\n"):
        return "must end with exactly one newline"
    if any(line != line.rstrip(" ") for line in text.split("\n")):
        return "must not have trailing spaces"
    if not _visible(text, CARD_TEXT_BAD):
        return "must not hold tabs, control, bidi, invisible or private-use characters"
    if ABSOLUTE_PATH.search(text):
        return "must not hold an absolute path"
    return None


def read_card(root: Path, file: Path, problems: list[str]) -> Card | None:
    path = file.relative_to(root).as_posix()
    parts = path.split("/")
    if any(part.startswith(".") for part in parts):
        problems.append(f"{path}: hidden files are refused")
        return None
    if len(parts) < 3 or parts[1] not in FOLDERS:
        problems.append(f"{path}: cards live in cards/{{{','.join(FOLDERS)}}}/")
        return None
    if not path.endswith(".md"):
        problems.append(f"{path}: a card is a .md file")
        return None
    kind = FOLDERS[parts[1]]
    inner = [*parts[2:-1], parts[-1][: -len(".md")]]
    data = file.read_bytes()
    if len(data) > MAX_CARD_BYTES:
        problems.append(f"{path}: a card is at most {MAX_CARD_BYTES} bytes")
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{path}: a card is UTF-8 text")
        return None
    problem = _card_text_problem(text)
    if problem:
        problems.append(f"{path}: {problem}")
        return None
    lines = text.split("\n")
    close = lines.index("---", 1) if lines[0] == "---" and "---" in lines[1:] else -1
    if close < 0:
        problems.append(f"{path}: a card starts with a frontmatter block between --- lines")
        return None
    fields: dict[str, str] = {}
    for line in lines[1:close]:
        match = LINE.fullmatch(line)
        if match is None:
            problems.append(f"{path}: frontmatter lines are exactly `key: value`: {line[:60]!r}")
            return None
        if match[1] in fields:
            problems.append(f"{path}: the field {match[1]} appears twice")
            return None
        fields[match[1]] = match[2]
    after = lines[close + 1:]
    if after == [""]:
        body = ""
    elif len(after) >= 3 and after[0] == "" and after[1] != "":
        body = "\n".join(after[1:])
    else:
        problems.append(f"{path}: after the closing --- leave one blank line, then the body")
        return None
    if card_text(fields, body) != text:
        problems.append(f"{path}: the card is not in its one exact form")
        return None
    slug = "/".join(inner) if kind == "protocol" else inner[-1]
    if len(slug) > 64 or any(len(part) > 64 for part in inner):
        problems.append(f"{path}: slugs, ids and folder names are at most 64 characters")
        return None
    if any(part.split(".")[0] in RESERVED for part in inner):
        problems.append(f"{path}: names must work on every system (no device names like con)")
        return None
    if kind == "protocol" and (PROTOCOL_ID.fullmatch(slug) is None or fields.get("id") != slug):
        problems.append(f"{path}: a protocol card lives at cards/protocols/<id>.md with that id")
        return None
    if kind != "protocol" and not all(SLUG.fullmatch(part) for part in inner):
        problems.append(f"{path}: names are lowercase letters, digits and single dashes")
        return None
    digest = hashlib.sha256(data).digest()
    return Card(kind, slug, path, fields, body, digest.hex(), chant(digest))


def check_card(card: Card) -> list[str]:
    fields, kind = card.fields, card.kind
    found: list[str] = []
    unknown = sorted(set(fields) - set(REQUIRED[kind]) - set(OPTIONAL[kind]))
    if unknown:
        found.append(f"unknown field(s): {', '.join(unknown)}")
    missing = [key for key in REQUIRED[kind] if key not in fields]
    for first, second in PAIRS if kind == "protocol" else ():
        if (first in fields) != (second in fields):
            missing.append(second if first in fields else first)
    if kind == "hive":
        present = [key for key in PINS if key in fields]
        if fields.get("status") != "planned" or present:
            missing.extend(key for key in PINS if key not in fields)
    if missing:
        found.append(f"missing pin(s) or field(s): {', '.join(missing)}")
    for key, value in fields.items():
        problem = value_problem(kind, key, value) if key not in unknown else None
        if problem:
            found.append(f"{key} {problem}")
    body_limit = 1000 if kind == "hive" else 4000
    if len(card.body) > body_limit:
        found.append(f"the body must be at most {body_limit} characters")
    if kind == "hive" and (not card.body or "\n\n" in card.body):
        found.append("the body of a hive card is exactly one short public paragraph")
    return [f"{card.path}: {problem}" for problem in found]


def _hive_md_problem(text: str) -> str | None:
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return "HIVE.md starts with a frontmatter block between --- lines"
    keys: dict[str, str] = {}
    for line in lines[1:lines.index("---", 1)]:
        match = re.fullmatch(r"([a-z][a-z0-9_]*):(?: (.*))?", line)
        if match and match[1] not in keys:
            keys[match[1]] = (match[2] or "").strip()
        elif not (re.fullmatch(r"  - \S.*", line) and list(keys)[-1:] == ["previous"]):
            return "HIVE.md frontmatter lines are `key: value` (previous: may list `  - id` items)"
    if set(keys) - HIVE_KEYS:
        return "HIVE.md frontmatter holds only " + ", ".join(sorted(HIVE_KEYS))
    if not keys.get("hive"):
        return "HIVE.md needs a hive: placeholder that the founder's Brainstem fills at create time"
    if keys.get("version") != "1":
        return "HIVE.md in a template starts at version: 1"
    if not re.fullmatch(r"[1-9][0-9]{0,8}", keys.get("approvals", "")):
        return "HIVE.md needs approvals: a whole number of at least 1"
    return None


def check_template(root: Path, folder: Path) -> list[str]:
    """A starter template obeys the hive-md file rules, plus README.md at its root."""
    problems: list[str] = []
    base = folder.relative_to(root).as_posix()
    seen: dict[str, str] = {}
    present: set[str] = set()
    for file in _walk(folder, root, problems):
        path = file.relative_to(folder).as_posix()
        parts = path.split("/")
        shown = f"{base}/{path}"
        for depth in range(1, len(parts) + 1):
            name = "/".join(parts[:depth])
            first = seen.setdefault(name.casefold(), name)
            if first != name:
                problems.append(f"{shown}: {name} and {first} differ only by case")
        if path in ("HIVE.md", ".gitattributes", "README.md"):
            present.add(path)
        elif parts[0] in ("members", "requests", "former"):
            problems.append(f"{shown}: a template holds no members/, requests/ or former/; "
                            "membership starts when the founder's Brainstem creates the Hive")
            continue
        elif parts[0] != "shared":
            problems.append(f"{shown}: a template root holds only HIVE.md, .gitattributes, "
                            "README.md and shared/")
            continue
        elif len(parts) < 3 or not path.endswith(".md") or len(path) > MAX_TEMPLATE_PATH:
            problems.append(f"{shown}: files sit in a folder under shared/, end in .md, and paths "
                            f"stay within {MAX_TEMPLATE_PATH} characters")
        for part in parts:
            if part == ".gitattributes" and path == ".gitattributes":
                continue
            if (SEGMENT.fullmatch(part) is None or part[-1] in " ."
                    or part.split(".")[0].rstrip(" ").lower() in RESERVED):
                problems.append(f"{shown}: names use letters, digits, space, dot, dash or "
                                "underscore, and work on every system (no hidden files)")
            if part.lower() in INSTRUCTION_NAMES:
                problems.append(f"{shown}: AI instruction file names are refused in a Hive")
        if os.name != "nt" and file.stat().st_mode & 0o111:
            problems.append(f"{shown}: executables are refused")
        data = file.read_bytes()
        if len(data) > MAX_TEMPLATE_FILE_BYTES:
            problems.append(f"{shown}: files are at most 1 MB")
            continue
        if path == ".gitattributes":
            if data != GITATTRIBUTES:
                problems.append(f"{shown}: must be exactly `* text eol=lf`")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{shown}: only UTF-8 text")
            continue
        if not _visible(text, HIVE_TEXT_BAD):
            problems.append(f"{shown}: no control, bidi, invisible or private-use characters")
        if DATAVIEWJS.search(text):
            problems.append(f"{shown}: no ```dataviewjs blocks or `$=` inline code")
        if ABSOLUTE_PATH.search(text):
            problems.append(f"{shown}: no absolute paths")
        if path == "HIVE.md":
            problem = _hive_md_problem(text)
            if problem:
                problems.append(f"{shown}: {problem}")
    for name in sorted({"HIVE.md", ".gitattributes", "README.md"} - present):
        problems.append(f"{base}/: a starter template needs {name}")
    return problems


def load(root: Path) -> tuple[str, str, str, list[Card]]:
    """Read and check the whole hub; returns the hub title, HUB.md text and sha256, and cards."""
    problems: list[str] = []
    hub_file = root / "HUB.md"
    if not hub_file.is_file() or hub_file.is_symlink():
        raise BuildError(["HUB.md: every hub has a HUB.md"])
    hub_bytes = hub_file.read_bytes()
    try:
        hub_text = hub_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise BuildError(["HUB.md: must be UTF-8 text"]) from None
    if hub_text.startswith("\ufeff") or "\r" in hub_text or not _visible(hub_text, HIVE_TEXT_BAD):
        problems.append("HUB.md: UTF-8 with LF line endings and no control or invisible characters")
    if ABSOLUTE_PATH.search(hub_text):
        problems.append("HUB.md: must not hold an absolute path")
    headings = (line[2:].strip() for line in hub_text.split("\n") if line.startswith("# "))
    title = next(headings, "Hub")
    for name in ("cards", "starters", "views"):
        if (root / name).is_symlink() or ((root / name).exists() and not (root / name).is_dir()):
            problems.append(f"{name}: must be a plain folder, not a link or a file")
    if problems:
        raise BuildError(problems)
    cards: list[Card] = []
    if (root / "cards").is_dir():
        for file in _walk(root / "cards", root, problems):
            card = read_card(root, file, problems)
            if card is not None:
                cards.append(card)
    by_slug: dict[tuple[str, str], Card] = {}
    for card in cards:
        other = by_slug.setdefault((card.kind, card.slug), card)
        if other is not card:
            problems.append(f"{card.path}: duplicate slug {card.slug}; also {other.path}")
        problems.extend(check_card(card))
    problems.extend(_cross_check(root, by_slug))
    folders = {(card.folder, "/".join(card.slug.split("/")[:depth])): card
               for card in cards for depth in range(1, card.slug.count("/") + 1)}
    for card in cards:
        for extension in (".json", ".html"):
            clash = folders.get((card.folder, card.slug + extension))
            if clash is not None:
                problems.append(f"{card.path}: its views would clash with {clash.path}")
    if problems:
        raise BuildError(problems)
    order = list(KINDS)
    cards.sort(key=lambda card: (order.index(card.kind), card.slug))
    return title, hub_text, hashlib.sha256(hub_bytes).hexdigest(), cards


def _cross_check(root: Path, by_slug: dict[tuple[str, str], Card]) -> list[str]:
    problems: list[str] = []

    def exists(kind: str, slug: str) -> bool:
        return (kind, slug) in by_slug

    for (kind, slug), card in sorted(by_slug.items()):
        fields = card.fields
        if kind == "hive":
            if "protocol" in fields and not exists("protocol", fields["protocol"]):
                problems.append(f"{card.path}: no protocol card {fields['protocol']}")
            if "org" in fields:
                org = by_slug.get(("organization", fields["org"]))
                if org is None:
                    problems.append(f"{card.path}: no organization card {fields['org']}")
                elif org.fields.get("hive") not in (slug, "template"):
                    problems.append(f"{card.path}: its org names another hive")
        if kind == "organization":
            hive = fields.get("hive", "template")
            if hive != "template" and not exists("hive", hive):
                problems.append(f"{card.path}: no hive card {hive}")
            if "starter" in fields:
                starter = by_slug.get(("starter", fields["starter"]))
                if starter is None:
                    problems.append(f"{card.path}: no starter card {fields['starter']}")
                elif starter.fields.get("org") != slug:
                    problems.append(f"{card.path}: its starter names another org")
        if kind == "starter" and "org" in fields and not exists("organization", fields["org"]):
            problems.append(f"{card.path}: no organization card {fields['org']}")
    named: dict[str, list[str]] = {}
    for (kind, _), card in sorted(by_slug.items()):
        match = TEMPLATE.fullmatch(card.fields.get("template", "")) if kind == "starter" else None
        if match:
            named.setdefault(match[1], []).append(card.path)
    starters = root / "starters"
    folders: dict[str, Path] = {}
    if starters.is_dir():
        with os.scandir(starters) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                    folders[entry.name] = Path(entry.path)
                else:
                    problems.append(f"starters/{entry.name}: starters/ holds only template folders")
    for name, paths in sorted(named.items()):
        if name not in folders:
            problems.append(f"{paths[0]}: no template folder starters/{name}/")
        elif len(paths) > 1:
            problems.append(f"starters/{name}/: named by more than one starter card")
    for name, folder in folders.items():
        if name not in named:
            problems.append(f"starters/{name}/: no starter card names this template")
        else:
            problems.extend(check_template(root, folder))
    return problems


# ---- views ----------------------------------------------------------------------------------

def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


INLINE = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n]+)\*\*")
LIST_ITEM = re.compile(r"(?:[-*]|\d+\.) ")


def _inline(text: str) -> str:
    out, position = [], 0
    for match in INLINE.finditer(text):
        out.append(_esc(text[position:match.start()]))
        if match[1] is not None:
            out.append(f"<code>{_esc(match[1])}</code>")
        elif match[2] is not None:
            link = match[3]
            out.append(f'<a href="{_esc(link)}" rel="noreferrer noopener">{_esc(match[2])}</a>'
                       if url_problem(link, ("https",)) is None else _esc(match[2]))
        else:
            out.append(f"<strong>{_esc(match[4])}</strong>")
        position = match.end()
    out.append(_esc(text[position:]))
    return "".join(out)


def _blocks(markdown: str) -> str:
    """A small, safe markdown subset: headings, paragraphs, lists and code blocks. No raw HTML."""
    out: list[str] = []
    paragraph: list[str] = []
    lines = markdown.split("\n")
    index = 0

    def flush() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        heading = re.match(r"(#{1,5}) (.+)", line)
        item = LIST_ITEM
        if line.startswith("```"):
            flush()
            end = index + 1
            while end < len(lines) and not lines[end].startswith("```"):
                end += 1
            out.append(f"<pre><code>{_esc(chr(10).join(lines[index + 1:end]))}</code></pre>")
            index = end + 1
        elif heading:
            flush()
            level = len(heading[1]) + 1
            out.append(f"<h{level}>{_inline(heading[2])}</h{level}>")
            index += 1
        elif item.match(line):
            flush()
            tag = "ol" if line[0].isdigit() else "ul"
            items: list[str] = []
            while index < len(lines) and (item.match(lines[index]) or (
                    items and lines[index].startswith("  ") and lines[index].strip())):
                if item.match(lines[index]):
                    items.append(item.sub("", lines[index], count=1))
                else:
                    items[-1] += " " + lines[index].strip()
                index += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(text)}</li>" for text in items)
                       + f"</{tag}>")
        elif not line.strip():
            flush()
            index += 1
        else:
            paragraph.append(line.strip())
            index += 1
    flush()
    return "\n".join(out)


STYLE = """body{margin:0;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
color:#1d232b;background:#fbfbf8}
header,main,footer{max-width:52rem;margin:0 auto;padding:1rem 1.25rem}
header{border-bottom:1px solid #d9dccf}
h1{margin:.2rem 0;font-size:1.8rem}h2{margin-top:2rem;font-size:1.3rem}
a{color:#1f5f99}code,pre{font:.9em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{overflow:auto;padding:.75rem;background:#f0f1ea;border-radius:.4rem}
ul.cards{list-style:none;padding:0}ul.cards li{padding:.45rem 0;border-bottom:1px solid #e6e8df}
.chip{display:inline-block;padding:0 .5rem;border-radius:1rem;font-size:.8rem;background:#e6e8df}
.chip.in-force{background:#cfeccf}.chip.specified{background:#d6e6f7}
.chip.experimental{background:#fbe7b5}.chip.candidate{background:#e8dcf5}
.chip.planned{background:#e4e4e4}.chip.frozen{background:#d9dee3;color:#465261}
.muted{color:#5b6570}table{border-collapse:collapse;width:100%}
th,td{text-align:left;vertical-align:top;padding:.35rem .5rem;border-bottom:1px solid #e6e8df;
word-break:break-word}
th{width:10rem;font-weight:600}
"""


CSP = "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"


def _page(title: str, depth: int, content: str) -> bytes:
    up = "../" * depth
    return (f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{_esc(title)}</title>
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
{content}
<footer class="muted">Generated by tools/build.py from the hub's cards. Nothing here runs.</footer>
</body>
</html>
""").encode()


def _chip(status: str) -> str:
    return f'<span class="chip {status.replace(" ", "-")}">{_esc(status)}</span>'


def _value(value: str) -> str:
    if url_problem(value, ("https",)) is None:
        return f'<a href="{_esc(value)}" rel="noreferrer noopener">{_esc(value)}</a>'
    return _esc(value) if " " in value else f"<code>{_esc(value)}</code>"


def _join_section(card: Card, cards: dict[tuple[str, str], Card], site_up: str) -> str:
    fields = card.fields
    steps: list[str] = []
    if card.kind == "hive" and fields.get("status") == "planned" and "root" not in fields:
        steps.append("This Hive is planned. It has no pins yet, so it cannot be joined.")
        steps.append(f"Channel: {_esc(fields['channel'])}")
    elif card.kind == "hive":
        protocol = cards.get(("protocol", fields["protocol"]))
        agent = protocol.fields.get("agent") if protocol else None
        name = _esc(fields["protocol"])
        link = f'<a href="{site_up}protocols/{name}.html">{name}</a>'
        steps.append(f"Check this card: its SHA-256 must equal the sha256 for {_esc(card.ref)} in "
                     f"<code>api/v2/index.json</code>: <code>{card.sha256}</code>.")
        steps.append(
            f"Give this card to your own Brainstem. Its Hive agent for {link}"
            + (f" (<a href=\"{_esc(agent)}\" rel=\"noreferrer noopener\">agent</a>, adopted by "
               "copy after you review it)" if agent else " (the protocol card pins no agent)")
            + " joins with this card's address, hive, root and founder: it clones the Hive, "
            "verifies the root and the founder fingerprint, writes one SSH-signed request file, "
            "and sends it the way the channel below says.")
        if "address" not in fields:
            steps.append("This card names no shared-copy address, so there is nothing to clone.")
        steps.append(f"Channel: {_esc(fields['channel'])}")
    elif card.kind == "protocol":
        if fields.get("status") == "frozen":
            steps.append("Frozen: start no new Hive with this protocol and join none.")
        if "agent" in fields:
            steps.append("To join a Hive that uses this protocol, your Brainstem needs its agent: "
                         f"{_value(fields['agent'])} "
                         f"(SHA-256 <code>{fields['agent_sha256']}</code>). Copy it into your "
                         "Brainstem's agents only after you have read it.")
        else:
            steps.append("No Brainstem agent is pinned for this protocol.")
        if "checker" in fields:
            steps.append(f"Anyone can verify a Hive with <code>{_esc(fields['checker'])}</code> "
                         f"(checker SHA-256 <code>{fields['checker_sha256']}</code>).")
    elif card.kind == "organization":
        hive = fields["hive"]
        where = ("from its starter template" if hive == "template" else
                 f'at <a href="{site_up}hives/{_esc(hive)}.html">{_esc(hive)}</a>')
        steps.append(f"An organization works in its Hive, {where}. Join that Hive with your own "
                     "Brainstem; the organization card itself grants nothing.")
        if "starter" in fields:
            steps.append(f'To start your own, use the starter '
                         f'<a href="{site_up}starters/{_esc(fields["starter"])}.html">'
                         f'{_esc(fields["starter"])}</a>.')
    else:
        template = fields["template"]
        steps.append(f"Pull <code>{_esc(template)}</code> down read-only: as a reference with your "
                     f"Hive agent's <code>reference</code>, with <code>npx degit</code> from this "
                     "hub's repository, or as a ZIP.")
        steps.append("Your Brainstem's Hive agent then creates a new Hive from it and fills the "
                     "<code>hive:</code> id. Members join that new Hive by request, as with any "
                     "Hive.")
    steps.append("The hub writes nothing into a Hive, keeps no subscription state, and runs "
                 "nothing.")
    return ("<h2>Join with your Brainstem</h2>\n<ol>"
            + "".join(f"<li>{step}</li>" for step in steps) + "</ol>")


def render(title: str, hub_text: str, hub_sha256: str, cards: list[Card]) -> dict[str, bytes]:
    views: dict[str, bytes] = {}
    by_slug = {(card.kind, card.slug): card for card in cards}
    by_chant: dict[str, list[Card]] = {}
    for card in cards:
        by_chant.setdefault(card.chant, []).append(card)
    collisions = {name: group for name, group in sorted(by_chant.items()) if len(group) > 1}

    def protocol_of(card: Card) -> str | None:
        if card.kind == "protocol":
            return card.slug
        if card.kind == "hive":
            return card.fields["protocol"]
        hive = by_slug.get(("hive", card.fields.get("hive", "")))
        return hive.fields["protocol"] if card.kind == "organization" and hive else None

    entries = []
    for card in cards:
        entries.append({
            "kind": card.kind, "slug": card.slug, "name": card.fields["name"],
            "status": card.fields["status"], "protocol": protocol_of(card), "chant": card.chant,
            "sha256": card.sha256, "path": card.path,
            "json": f"api/v2/{card.folder}/{card.slug}.json",
            "page": f"site/{card.folder}/{card.slug}.html",
        })
        views[f"views/api/v2/{card.folder}/{card.slug}.json"] = _json({
            "kind": card.kind, "slug": card.slug, "path": card.path, "sha256": card.sha256,
            "chant": card.chant, "frontmatter": card.fields, "body": card.body,
        })
    views["views/api/v2/index.json"] = _json({
        "api": API,
        "hub": {"title": title, "path": "HUB.md", "sha256": hub_sha256},
        "cards": entries,
        "collisions": [{"chant": name, "cards": [card.ref for card in group]}
                       for name, group in collisions.items()],
    })

    lines = [f"# Chants for {title}: seven words from the first seven bytes of each card's "
             "SHA-256.",
             "# A chant is a locator, never authority. Check the card's full sha256 in "
             "api/v2/index.json.",
             "# A chant that two or more cards share is a collision, marked COLLISION.", ""]
    for card in sorted(cards, key=lambda item: (item.chant, item.ref)):
        mark = "  COLLISION" if card.chant in collisions else ""
        lines.append(f"{card.chant}  {card.ref}  sha256:{card.sha256}{mark}")
    views["views/chants.txt"] = ("\n".join(lines) + "\n").encode("utf-8")

    views["views/site/style.css"] = STYLE.encode()
    sections = []
    for kind, (folder, heading) in KINDS.items():
        group = [card for card in cards if card.kind == kind]
        if not group:
            continue
        items = "".join(
            f'<li><a href="{folder}/{_esc(card.slug)}.html">{_esc(card.fields["name"])}</a> '
            f'{_chip(card.fields["status"])} <code class="muted">{card.chant}</code>'
            + (f' <span class="muted">· {_esc(protocol_of(card) or "")}</span>'
               if kind != "protocol" and protocol_of(card) else "")
            + "</li>" for card in group)
        sections.append(f"<section><h2>{heading}</h2><ul class=\"cards\">{items}</ul></section>")
    if collisions:
        rows = "".join(
            f"<li><code>{name}</code>: " + ", ".join(
                f'<a href="{card.folder}/{_esc(card.slug)}.html">{_esc(card.ref)}</a>'
                for card in group) + "</li>" for name, group in collisions.items())
        sections.append("<section id=\"collisions\"><h2>Chant collisions</h2><p>These cards share "
                        "a chant. Use the full sha256 to tell them apart.</p>"
                        f"<ul>{rows}</ul></section>")
    hub_lines = hub_text.split("\n")
    title_line = next((index for index, line in enumerate(hub_lines) if line.startswith("# ")), -1)
    about = "\n".join(line for index, line in enumerate(hub_lines) if index != title_line)
    views["views/site/index.html"] = _page(title, 0, (
        f"<header><h1>{_esc(title)}</h1>\n<p>A hub is a tree of markdown cards, one fact per "
        "file. Nothing in a hub runs; you join a Hive with your own Brainstem.</p>\n"
        '<p><a href="../api/v2/index.json">api/v2/index.json</a> · '
        '<a href="../chants.txt">chants.txt</a></p></header>\n<main>\n'
        + "\n".join(sections)
        + f"\n<section><h2>About this hub</h2>\n{_blocks(about)}\n</section>\n</main>"))

    for card in cards:
        depth = 1 + card.slug.count("/")
        up = "../" * depth
        pins = "".join(f"<tr><th>{_esc(key)}</th><td>{_value(value)}</td></tr>"
                       for key, value in card.fields.items() if key not in ("card", "name"))
        shared = collisions.get(card.chant)
        note = ("<p><strong>Chant collision:</strong> this chant also names "
                + ", ".join(_esc(other.ref) for other in shared if other is not card)
                + ". Use the full sha256.</p>") if shared else ""
        content = (
            f'<header><p><a href="{up}index.html">{_esc(title)}</a> · {_esc(KINDS[card.kind][1])}'
            f"</p><h1>{_esc(card.fields['name'])}</h1><p>{_chip(card.fields['status'])} "
            f"<code class=\"muted\">{card.chant}</code></p></header>\n<main>\n"
            f"{_blocks(card.body)}\n<h2>Pins</h2>\n<table>{pins}</table>\n"
            f"<p class=\"muted\">sha256 <code>{card.sha256}</code> · source "
            f"<code>{_esc(card.path)}</code> · <a href=\"{up}../api/v2/{card.folder}/"
            f"{_esc(card.slug)}.json\">JSON</a></p>\n{note}"
            f"{_join_section(card, by_slug, up)}\n</main>")
        views[f"views/site/{card.folder}/{card.slug}.html"] = _page(card.fields["name"], depth,
                                                                     content)
    return views


def build(root: Path) -> dict[str, bytes]:
    """Check the hub at root and return every view as {path: bytes}, without writing."""
    if hashlib.sha256("\n".join(WORDS).encode("utf-8")).hexdigest() != WORDS_SHA256:
        raise BuildError(["tools/build.py: the chant vocabulary does not match its SHA-256"])
    return render(*load(root))


def _views_problems(root: Path) -> list[str]:
    folder = root / "views"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        return ["views: must be a plain folder, not a link or a file"]
    return []


def differences(root: Path, views: dict[str, bytes]) -> list[str]:
    problems = _views_problems(root)
    if problems:
        return problems
    folder = root / "views"
    existing = ({path.relative_to(root).as_posix(): path for path in _walk(folder, root, problems)}
                if folder.is_dir() else {})
    for path in sorted(views):
        if path not in existing:
            problems.append(f"{path}: missing")
        elif existing[path].read_bytes() != views[path]:
            problems.append(f"{path}: differs from a fresh build")
    extra = sorted(set(existing) - set(views))
    problems.extend(f"{path}: not generated by the builder" for path in extra)
    return problems


def _remove_empty_folders(folder: Path) -> None:
    for directory in sorted((item for item in folder.rglob("*") if item.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def write(root: Path, views: dict[str, bytes]) -> None:
    folder = root / "views"
    problems = _views_problems(root)
    existing = _walk(folder, root, problems) if folder.is_dir() and not problems else []
    if problems:
        raise BuildError(problems)
    for stale in existing:
        if stale.relative_to(root).as_posix() not in views:
            stale.unlink()
    if folder.is_dir():
        _remove_empty_folders(folder)
    for name, data in views.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)
    _remove_empty_folders(folder)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a hub's cards and build its views.")
    parser.add_argument("--check", action="store_true",
                        help="rebuild in memory and compare with views/ byte for byte")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="the hub folder (default: the folder above tools/)")
    args = parser.parse_args(argv)
    try:
        views = build(args.root)
        if args.check:
            problems = differences(args.root, views)
            if problems:
                raise BuildError([*problems, "views/ is out of date: run python tools/build.py"])
        else:
            write(args.root, views)
    except BuildError as error:
        print("\n".join(error.problems), file=sys.stderr)
        print(f"refused: {len(error.problems)} problem(s)", file=sys.stderr)
        return 1
    cards = sum(1 for path in views if path.startswith("views/api/v2/") and path.count("/") > 3)
    print(f"{'checked' if args.check else 'built'} {len(views)} view files from {cards} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
