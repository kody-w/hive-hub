#!/usr/bin/env python3
"""Regenerate the deterministic Hive Hub agent.lock from reviewed constants."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "hive-hub"
sys.path.insert(0, str(ROOT))

from adapters.github import GITHUB_FINGERPRINT  # noqa: E402


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


SUBSCRIPTION_CONTRACT = {
    "schema": "hive-hub-adapter-contract/1",
    "id": "hive-hub.subscription/1",
    "input": "verified-hive-declaration",
    "effect": "one-device-local-subscription",
    "network_after_resolution": False,
    "executes_downloaded_content": False,
    "remote_write": False,
    "reversible": True,
}

GITHUB_SUBSCRIPTION_CONTRACT = {
    "schema": "hive-hub-adapter-contract/1",
    "id": "hive-hub.github-repository/1",
    "input": "verified-hive-declaration",
    "source_adapter": "github-repository",
    "source_fingerprint": GITHUB_FINGERPRINT.value,
    "effect": "one-device-local-subscription",
    "network_after_resolution": False,
    "executes_downloaded_content": False,
    "remote_write": False,
    "reversible": True,
}

def build_lock() -> dict[str, object]:
    files = []
    for path in sorted(item for item in SKILL.rglob("*") if item.is_file()):
        if path.name == "agent.lock":
            continue
        data = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(SKILL).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return {
        "schema": "hive-hub-agent-lock/1",
        "name": "hive-hub",
        "version": "0.1.0",
        "runner": {
            "python": ">=3.11",
            "isolated": True,
            "stdlib_only": True,
        },
        "limits": {
            "card_bytes": 65_536,
            "dialbook_bytes": 4_194_304,
            "dialbook_records": 4096,
            "json_bytes": 1_048_576,
            "json_depth": 32,
            "json_nodes": 20_000,
            "git_output_bytes": 4_194_304,
            "learning_items": 64,
            "learning_item_bytes": 33_554_432,
            "process_seconds": 600,
        },
        "trusted_static_origins": [
            "https://kody-w.github.io",
        ],
        "adapters": [
            {
                "id": SUBSCRIPTION_CONTRACT["id"],
                "fingerprint": digest(SUBSCRIPTION_CONTRACT),
                "contract": SUBSCRIPTION_CONTRACT,
                "implementation": "local-subscription",
            },
            {
                "id": GITHUB_SUBSCRIPTION_CONTRACT["id"],
                "fingerprint": digest(GITHUB_SUBSCRIPTION_CONTRACT),
                "contract": GITHUB_SUBSCRIPTION_CONTRACT,
                "implementation": "local-subscription",
            },
        ],
        "files": files,
    }


def encoded_lock() -> str:
    return (
        json.dumps(build_lock(), ensure_ascii=False, indent=2, sort_keys=False)
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in ([], ["--check"]):
        print("usage: update_agent_lock.py [--check]", file=sys.stderr)
        return 2
    expected = encoded_lock()
    target = SKILL / "agent.lock"
    if arguments == ["--check"]:
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            print("agent.lock is out of date", file=sys.stderr)
            return 1
        print("agent.lock is current")
        return 0
    target.write_text(
        expected,
        encoding="utf-8",
        newline="\n",
    )
    print(f"updated {target} ({len(build_lock()['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
