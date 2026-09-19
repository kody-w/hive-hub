"""Original offline CSV preflight. Findings are not an accounting certification."""

import argparse
import csv
import io
import json
from pathlib import Path

MAX_BYTES = 1_048_576
MAX_ROWS = 10_000


def analyze_text(text, required=(), key=None):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("CSV exceeds 1 MiB")
    if "\x00" in text:
        raise ValueError("NUL bytes are not supported")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise ValueError("malformed CSV") from exc
    if not rows or not rows[0]:
        raise ValueError("CSV needs a header")
    if len(rows) - 1 > MAX_ROWS:
        raise ValueError("CSV exceeds 10000 records")
    header = rows[0]
    findings = []

    def add(code, record, column=None):
        finding = {"code": code, "record": record}
        if column is not None:
            finding["column"] = column
        findings.append(finding)

    for index, name in enumerate(header):
        if not name.strip():
            add("blank-header", 1, index + 1)
        if name in header[:index]:
            add("duplicate-header", 1, index + 1)
    for name in required:
        if name not in header:
            add("missing-required-column", 1)
    if key and header.count(key) != 1:
        add("invalid-key-column", 1)
    required_indexes = [header.index(name) for name in required if header.count(name) == 1]
    key_index = header.index(key) if key and header.count(key) == 1 else None
    seen = set()
    for record, row in enumerate(rows[1:], 2):
        if len(row) != len(header):
            add("ragged-row", record)
            continue
        for index in required_indexes:
            if not row[index].strip():
                add("blank-required-value", record, index + 1)
        if key_index is not None:
            value = row[key_index].strip()
            if not value:
                add("blank-key", record, key_index + 1)
            elif value in seen:
                add("duplicate-key", record, key_index + 1)
            seen.add(value)
        for index, value in enumerate(row):
            if value.lstrip().startswith(("=", "+", "-", "@")):
                add("spreadsheet-formula-risk", record, index + 1)
    return {"artifact_kind": "reference-preflight", "records": len(rows) - 1, "ok": not findings, "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--columns", nargs="*", default=[])
    parser.add_argument("--key")
    args = parser.parse_args()
    try:
        with args.csv_file.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("CSV exceeds 1 MiB")
        result = analyze_text(raw.decode("utf-8-sig"), args.columns, args.key)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
