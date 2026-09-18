#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.file_integrity import FileIntegrityError, read_regular_bytes  # noqa: E402

SAFE_DENY_DIGESTS = frozenset(
    {
        "18bd7d72c25c6360e675996cf605328e499729c72c6035d55a4cbaf05992327c",
        "30c31ea528886a0b83fa156fe7f5e8da4a7fde32f0a3ad8a6fd83d6fae765cd2",
    }
)
PRIVATE_DENY_ENV = "HIVE_HUB_PRIVATE_IDENTIFIER_DENY_SHA256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}"
    r"(?:/[A-Za-z0-9][A-Za-z0-9_.-]{1,127})?"
    r"(?![A-Za-z0-9_.-])"
)
LOCAL_PATH_RE = re.compile(r"(?:/Users/[A-Za-z0-9._-]+/|[A-Za-z]:/Users/[A-Za-z0-9._-]+/)")
SECRET_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16})"
)
PUBLIC_PREFIXES = (
    ".well-known/",
    "api/",
    "hub/",
    "llms.txt",
    "public-src/",
    "skills/hive-hub/registry/",
)
ALLOWED_PUBLIC_REPOSITORIES = {
    "billwhalenmsft/softwarecoellc-vteam-hive",
    "kody-w/hive-hub",
}
GITHUB_REPOSITORY_RE = re.compile(
    r"(?:https://(?:raw\.)?githubusercontent\.com/|https://github\.com/)"
    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)


def tracked_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    )
    return sorted(
        path for path in output.splitlines() if path
    )


def text(path: Path) -> str | None:
    data = read_regular_bytes(path)
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def deny_digests() -> frozenset[str]:
    supplied = {
        item.casefold()
        for item in re.split(r"[\s,]+", os.environ.get(PRIVATE_DENY_ENV, ""))
        if item
    }
    if any(SHA256_RE.fullmatch(item) is None for item in supplied):
        raise ValueError(f"{PRIVATE_DENY_ENV} must contain only lowercase SHA-256 digests")
    return SAFE_DENY_DIGESTS | supplied


def contains_denied_identifier(content: str, denied: frozenset[str]) -> bool:
    candidates = [match.group(0) for match in IDENTIFIER_CANDIDATE_RE.finditer(content)]
    candidates.extend(
        match.group(1).removesuffix(".git")
        for match in GITHUB_REPOSITORY_RE.finditer(content)
    )
    for candidate in candidates:
        for normalized in {candidate, candidate.casefold()}:
            if hashlib.sha256(normalized.encode("utf-8")).hexdigest() in denied:
                return True
    return False


def check() -> list[str]:
    failures: list[str] = []
    denied = deny_digests()
    for relative in tracked_paths():
        try:
            content = text(ROOT / relative)
        except FileIntegrityError as exc:
            failures.append(f"{relative}: {exc}")
            continue
        if content is None:
            continue
        if contains_denied_identifier(content, denied):
            failures.append(f"{relative}: contains a denied private identifier digest match")
        if LOCAL_PATH_RE.search(content):
            failures.append(f"{relative}: contains a local personal path")
        if SECRET_RE.search(content):
            failures.append(f"{relative}: contains credential- or key-shaped material")
        if relative.startswith(PUBLIC_PREFIXES):
            for match in GITHUB_REPOSITORY_RE.finditer(content):
                repository = match.group(1).removesuffix(".git")
                if repository not in ALLOWED_PUBLIC_REPOSITORIES:
                    failures.append(
                        f"{relative}: public surface references unapproved repository {repository}"
                    )
    return sorted(set(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    failures = check()
    if failures:
        print("\n".join(failures))
        return 1
    print("public release privacy scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
