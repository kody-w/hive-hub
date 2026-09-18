from __future__ import annotations

from pathlib import Path

from hive_hub.canonical import canonical_bytes
from hive_hub.schema_catalog import SCHEMAS


def main() -> None:
    target = Path(__file__).parents[1] / "src" / "hive_hub" / "schema"
    target.mkdir(parents=True, exist_ok=True)
    expected = {f"{name}.schema.json" for name in SCHEMAS}
    for stale in target.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()
    for name, schema in sorted(SCHEMAS.items()):
        (target / f"{name}.schema.json").write_bytes(canonical_bytes(schema) + b"\n")


if __name__ == "__main__":
    main()
