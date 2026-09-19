"""Index, search, timeline and audit only the original local synthetic corpus."""
import argparse
import csv
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_FILES = (
    "sources/announcements.csv", "sources/release-notes.csv",
    "sources/lab-notes.csv", "sources/support-notices.csv"
)
BENCHMARK_FILE = "sources/benchmark-runs.csv"
SOURCE_FILES = DOCUMENT_FILES + (BENCHMARK_FILE,)
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def read_json(relative):
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if value.get("classification") != "SYNTHETIC":
        raise ValueError("Only SYNTHETIC inputs are supported")
    return value


def csv_rows(relative):
    with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("Invalid CSV header")
        rows = list(reader)
    if not rows:
        raise ValueError("Empty evidence file")
    for row in rows:
        if None in row or any(value is None or "\n" in value or "\r" in value for value in row.values()):
            raise ValueError("Each source record must occupy one complete physical CSV row")
        if row.get("classification") != "SYNTHETIC":
            raise ValueError("Non-synthetic evidence refused")
    return rows


def valid_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use exact ISO calendar dates")
    return date.fromisoformat(value)


def whole_number(value):
    if not re.fullmatch(r"0|[1-9]\d*", value):
        raise ValueError("Nonnegative integer count required")
    return int(value)


def benchmark_metrics(row):
    attempted, acknowledged = whole_number(row["attempted"]), whole_number(row["acknowledged"])
    hours = Decimal(row["offline_hours"])
    if not hours.is_finite() or hours < 0 or attempted <= 0 or acknowledged > attempted:
        raise ValueError("Invalid benchmark counts or duration")
    if row["cold_restart"] not in ("0", "1"):
        raise ValueError("Invalid restart flag")
    recovered = None if row["recovered_ids"] == "" else whole_number(row["recovered_ids"])
    if recovered is not None and recovered > acknowledged:
        raise ValueError("Recovered IDs cannot exceed acknowledged IDs in this fixture")
    return {
        "record_id": row["record_id"], "offline_hours": str(hours),
        "cold_restart": row["cold_restart"] == "1", "attempted": attempted,
        "acknowledged": acknowledged, "acknowledgment_fraction": str(Decimal(acknowledged) / attempted),
        "recovered_ids": recovered,
        "acknowledged_ids_unreconciled": None if recovered is None else acknowledged - recovered,
        "condition": row["condition"],
        "meets_duration_restart_recovery_gate": bool(
            hours >= 72 and row["cold_restart"] == "1" and attempted >= 400
            and acknowledged > 0 and recovered is not None and recovered == acknowledged
        )
    }


def load_corpus():
    as_of = valid_date(read_json("case/question.json")["as_of"])
    records, ids = [], set()
    for relative in SOURCE_FILES:
        digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for number, fields in enumerate(csv_rows(relative), start=2):
            record_id = fields["record_id"]
            if not ID_PATTERN.fullmatch(record_id) or record_id in ids:
                raise ValueError("Duplicate or invalid source record ID")
            ids.add(record_id)
            published = valid_date(fields["published_at"])
            if published > as_of:
                raise ValueError("Future-dated evidence exceeds the case's as-of boundary")
            if relative == BENCHMARK_FILE:
                metrics = benchmark_metrics(fields)
                text = f'{fields["build"]}: {fields["condition"]}; {metrics["acknowledged"]}/{metrics["attempted"]} acknowledged; offline {fields["offline_hours"]} hours.'
                title = f'Benchmark {record_id}'
            else:
                text, title = fields["statement"], fields["title"]
            records.append({
                "record_id": record_id, "published_at": fields["published_at"],
                "title": title, "text": text, "origin_group": fields["origin_group"],
                "source_file": relative, "csv_row": number,
                "citation": f"{relative}#row={number}", "source_sha256": digest,
                "classification": "SYNTHETIC", "original_fields": fields
            })
    return records


def timeline(records):
    return sorted(records, key=lambda row: (row["published_at"], row["citation"]))


def search(records, query):
    term = query.strip().casefold()
    if not term or len(term) > 200:
        raise ValueError("Search requires 1–200 characters")
    return [row for row in timeline(records) if term in (row["record_id"] + " " + row["title"] + " " + row["text"]).casefold()]


def resolve_refs(text, index):
    refs = text.split(";")
    if not refs or len(set(refs)) != len(refs) or any(ref not in index for ref in refs):
        raise ValueError(f"Unresolved, repeated, or non-allowlisted citation: {text}")
    return [index[ref] for ref in refs]


def audit(records=None):
    records = load_corpus() if records is None else records
    index = {row["citation"]: row for row in records}
    if len(index) != len(records) or len({row["record_id"] for row in records}) != len(records):
        raise ValueError("Duplicate source identity or citation")
    hypotheses = read_json("analysis/hypotheses.json")["hypotheses"]
    hypothesis_ids = {row["id"] for row in hypotheses}
    if len(hypothesis_ids) != len(hypotheses):
        raise ValueError("Duplicate hypothesis ID")
    claims = csv_rows("analysis/claims.csv")
    claim_ids = set()
    for claim in claims:
        if claim["claim_id"] in claim_ids or claim["hypothesis_id"] not in hypothesis_ids:
            raise ValueError("Duplicate claim or unknown hypothesis")
        claim_ids.add(claim["claim_id"])
        if claim["relationship"] not in ("supports", "contradicts", "neutral") or claim["confidence"] not in ("low", "medium", "high"):
            raise ValueError("Invalid qualitative claim code")
        resolve_refs(claim["source_refs"], index)
    conflicts = csv_rows("analysis/contradictions.csv")
    conflict_ids = set()
    for conflict in conflicts:
        if conflict["conflict_id"] in conflict_ids or conflict["kind"] not in ("direct-scope-conflict", "schedule-ambiguity", "metric-mismatch"):
            raise ValueError("Invalid conflict code")
        conflict_ids.add(conflict["conflict_id"])
        resolve_refs(conflict["left_ref"], index)
        resolve_refs(conflict["right_ref"], index)
    board = csv_rows("ops/investigation-board.csv")
    if len({row["inquiry_id"] for row in board}) != len(board):
        raise ValueError("Duplicate inquiry")
    if any(row["current_state"] != "prospective-not-collected" for row in board):
        raise ValueError("Reference inquiries must not claim completed collection")
    metrics = []
    for row in records:
        if row["source_file"] == BENCHMARK_FILE:
            metrics.append({**benchmark_metrics(row["original_fields"]), "citation": row["citation"]})
    return {
        "classification": "SYNTHETIC", "source_files": len({row["source_file"] for row in records}),
        "source_records": len(records), "coded_claims": len(claims), "conflict_cases": len(conflicts),
        "prospective_inquiries": len(board), "references_resolve": True,
        "origin_groups": sorted({row["origin_group"] for row in records}),
        "independence_caution": "Origin labels are not independent votes; lab-style runs used a supplied device/build.",
        "run_metrics": metrics, "qualifying_runs": sum(row["meets_duration_restart_recovery_gate"] for row in metrics),
        "pooled_reliability": None, "pooling_limit": "Unlike durations/restart conditions must not be pooled into a reliability estimate.",
        "decision_limit": "No procurement, deployment, launch-readiness, or real-source claim follows from this authored corpus.",
        "external_effects": []
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("index", "timeline", "audit"):
        sub.add_parser(name)
    search_parser = sub.add_parser("search")
    search_parser.add_argument("query")
    args = parser.parse_args()
    records = load_corpus()
    if args.command == "audit":
        output = audit(records)
    else:
        result = records if args.command == "index" else timeline(records) if args.command == "timeline" else search(records, args.query)
        output = {"classification": "SYNTHETIC", "command": args.command, "count": len(result), "records": result, "external_effects": []}
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
