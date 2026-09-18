from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hive_hub import DialRecord, HiveHub, PrivateAccessPolicy
from hive_hub.errors import ConflictError
from hive_hub.store import PrivateDialbook


def main() -> int:
    home, record_path, policy_path, attempted_path, entered_path, result_path = map(
        Path,
        sys.argv[1:],
    )
    record = DialRecord.from_dict(json.loads(record_path.read_text(encoding="utf-8")))
    policy = PrivateAccessPolicy.from_dict(
        json.loads(policy_path.read_text(encoding="utf-8"))
    )
    original_transaction = PrivateDialbook.registration_transaction
    original_apply = PrivateDialbook.apply

    @contextmanager
    def instrumented_transaction(
        dialbook: PrivateDialbook,
        record_id: str,
    ) -> Iterator[None]:
        attempted_path.write_text("attempting\n", encoding="utf-8")
        with original_transaction(dialbook, record_id):
            yield

    def instrumented_apply(dialbook: PrivateDialbook, plan: object) -> bool:
        entered_path.write_text("entered\n", encoding="utf-8")
        return original_apply(dialbook, plan)  # type: ignore[arg-type]

    PrivateDialbook.registration_transaction = instrumented_transaction
    PrivateDialbook.apply = instrumented_apply  # type: ignore[method-assign]
    try:
        HiveHub(home).register_private_record(record, policy=policy)
    except ConflictError:
        result_path.write_text("conflict\n", encoding="utf-8")
        return 0
    result_path.write_text("registered\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
