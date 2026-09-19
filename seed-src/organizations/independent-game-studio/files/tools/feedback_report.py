"""Summarize original synthetic playtest records without writing or networking."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]


def summarize(rows):
    if not rows:
        raise ValueError("At least one synthetic session is required")
    ids = set()
    for row in rows:
        if row["classification"] != "SYNTHETIC" or row["session_id"] in ids:
            raise ValueError("Expected uniquely identified SYNTHETIC records")
        ids.add(row["session_id"])
        for field in ("completed", "bridge_stall", "discovered_undo"):
            if row[field] not in ("0", "1"):
                raise ValueError("Invalid binary observation")
        if int(row["actions"]) < 0 or not 1 <= int(row["confidence_1_to_5"]) <= 5:
            raise ValueError("Observation is outside its valid range")
    completed = [row for row in rows if row["completed"] == "1"]
    return {
        "classification": "SYNTHETIC",
        "records": len(rows),
        "completions": len(completed),
        "completion_fraction": len(completed) / len(rows),
        "bridge_stalls": sum(int(row["bridge_stall"]) for row in rows),
        "undo_discoveries": sum(int(row["discovered_undo"]) for row in rows),
        "mean_completed_actions": mean(int(row["actions"]) for row in completed) if completed else None,
        "mean_confidence": mean(int(row["confidence_1_to_5"]) for row in rows),
        "evidence_limit": "Authored exercise only; not observed research or market validation."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    with (ROOT / "data/playtests.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = summarize(rows)
    if args.self_test:
        assert (report["records"], report["completions"], report["bridge_stalls"], report["undo_discoveries"]) == (8, 5, 5, 3)
        assert report["mean_completed_actions"] == 54.4
        for bad in ([], [rows[0], rows[0]], [{**rows[0], "classification": "OBSERVED"}], [{**rows[0], "completed": "2"}]):
            try:
                summarize(bad)
            except ValueError:
                continue
            raise AssertionError("Invalid data was accepted")
        print("PASS: synthetic baseline plus four invalid-input cases")
    else:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
