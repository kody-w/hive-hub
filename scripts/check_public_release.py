#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_LITERALS = (
    "kody-w/" + "microsol-organization",
    "kody-w-" + "fresh-device-onboarding",
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
        path for path in output.splitlines() if path and (ROOT / path).is_file()
    )


def text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check() -> list[str]:
    failures: list[str] = []
    for relative in tracked_paths():
        content = text(ROOT / relative)
        if content is None:
            continue
        for forbidden in FORBIDDEN_LITERALS:
            if forbidden in content:
                failures.append(f"{relative}: contains prohibited private locator")
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
