from __future__ import annotations

import json
from pathlib import Path

ADAPTERS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ADAPTERS_ROOT / "fixtures"


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
