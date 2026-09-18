#!/usr/bin/env python3
"""Prove the locked skill works from its repository and as a copied folder."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "hive-hub"
WORK = ROOT / "tests" / ".work" / "prove"


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result


def main() -> int:
    run([sys.executable, str(ROOT / "scripts" / "check.py")])
    run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "tests.test_hive_hub",
            "-v",
        ]
    )
    shutil.rmtree(WORK, ignore_errors=True)
    copied = WORK / "copied hive-hub"
    copied.parent.mkdir(parents=True)
    shutil.copytree(SKILL, copied)
    verified = run(
        [
            sys.executable,
            "-I",
            "-B",
            str(copied / "scripts" / "run.py"),
            "verify",
        ],
        cwd=WORK,
    )
    value = json.loads(verified.stdout)
    if value.get("status") != "verified" or value.get("ready") is not True:
        raise RuntimeError("copied folder did not verify")
    decoded = run(
        [
            sys.executable,
            "-I",
            "-B",
            str(copied / "scripts" / "run.py"),
            "decode",
            "--locator",
            "example/hive at main",
        ],
        cwd=WORK,
    )
    if json.loads(decoded.stdout).get("status") != "decoded":
        raise RuntimeError("copied folder did not decode a locator")
    shutil.rmtree(WORK, ignore_errors=True)
    print("PASS prove: tests green and copied skill folder operates independently")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        shutil.rmtree(WORK, ignore_errors=True)
        print(f"FAIL prove: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
