#!/usr/bin/env python3
"""Check the Hive Hub skill package without third-party tools."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.file_integrity import read_regular_bytes  # noqa: E402

SKILL = ROOT / "skills" / "hive-hub"
RUNNER = SKILL / "scripts" / "run.py"
SIX_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def frontmatter_fields(text: str) -> set[str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        fail("SKILL.md has no closed frontmatter")
    block = text.split("---\n", 2)[1]
    return {
        line.split(":", 1)[0]
        for line in block.splitlines()
        if line and not line.startswith(" ")
    }


def main() -> int:
    skill_text = read_regular_bytes(SKILL / "SKILL.md").decode("utf-8")
    if frontmatter_fields(skill_text) != SIX_FIELDS:
        fail("SKILL.md does not use exactly the six Agent Skills fields")
    lowered = skill_text.casefold()
    for phrase in (
        "dial this hive",
        "join this hive on this device and tell me when you are ready",
        "camera",
        "qr",
    ):
        if phrase not in lowered:
            fail(f"SKILL.md is missing trigger phrase {phrase!r}")
    tree = ast.parse(read_regular_bytes(RUNNER).decode("utf-8"), filename=str(RUNNER))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    non_stdlib = sorted(imported - sys.stdlib_module_names - {"__future__"})
    if non_stdlib:
        fail("runner imports non-stdlib modules: " + ", ".join(non_stdlib))
    lock = json.loads(read_regular_bytes(SKILL / "agent.lock").decode("utf-8"))
    if lock.get("schema") != "hive-hub-agent-lock/1":
        fail("agent.lock schema is not recognized")
    commands = [
        [sys.executable, str(ROOT / "scripts" / "update_agent_lock.py"), "--check"],
        [sys.executable, "-I", "-B", str(RUNNER), "verify"],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            fail((result.stderr or result.stdout).strip())
    print("PASS check: six fields, current lock, isolated stdlib runner")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"FAIL check: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
