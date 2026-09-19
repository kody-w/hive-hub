"""Original bounded offline allocation example; all scores are assumptions."""

import argparse
import csv
import itertools
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


def money(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("money must be a decimal amount") from exc
    if not amount.is_finite() or not 0 <= amount <= Decimal("1000000000") or amount != amount.quantize(Decimal("0.01")):
        raise ValueError("money must be within 0..1000000000 with at most two decimal places")
    return int(amount * 100)


def integer(value, low, high, label):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"{label} must be an integer")
    result = int(value)
    if not low <= result <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return result


def normalize(rows, capacity):
    if not 1 <= len(rows) <= 18:
        raise ValueError("supply between 1 and 18 candidate experiments")
    if capacity.get("classification") != "SYNTHETIC" or any(row.get("classification") != "SYNTHETIC" for row in rows):
        raise ValueError("this reference requires explicitly SYNTHETIC planning inputs")
    hours = integer(capacity["founder_hours"], 1, 168, "founder_hours")
    reserve = integer(capacity["reserved_hours"], 0, hours, "reserved_hours")
    cash = money(capacity["cash_usd"])
    reserved_cash = money(capacity["reserved_cash_usd"])
    if reserved_cash > cash:
        raise ValueError("cash reserve exceeds cash")
    limits = {
        "hours": hours - reserve,
        "cost_cents": cash - reserved_cash,
        "active_businesses": integer(capacity["max_active_businesses"], 1, 12, "max_active_businesses"),
    }
    candidates = []
    seen = set()
    for row in rows:
        identity, unit = row["experiment-id"], row["unit"]
        if not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", x) for x in (identity, unit)):
            raise ValueError("experiment and unit IDs must be lowercase-hyphenated")
        if identity in seen:
            raise ValueError("duplicate experiment ID")
        seen.add(identity)
        learning = integer(row["learning-points"], 1, 5, "learning-points")
        reuse = integer(row["reuse-points"], 1, 5, "reuse-points")
        confidence = integer(row["confidence-pct"], 0, 100, "confidence-pct")
        candidates.append({
            "id": identity, "unit": unit,
            "hours": integer(row["hours"], 1, 168, "hours"),
            "cost_cents": money(row["cost-usd"]),
            "score_units": (3 * learning + 2 * reuse) * confidence,
            "selected": integer(row["selected"], 0, 1, "selected") == 1,
        })
    return sorted(candidates, key=lambda row: row["id"]), limits


def summarize(selection, limits):
    hours = sum(row["hours"] for row in selection)
    cents = sum(row["cost_cents"] for row in selection)
    units = sorted({row["unit"] for row in selection})
    violations = []
    if hours > limits["hours"]:
        violations.append("hours")
    if cents > limits["cost_cents"]:
        violations.append("cash")
    if len(units) > limits["active_businesses"]:
        violations.append("active-businesses")
    if len(units) != len(selection):
        violations.append("multiple-experiments-per-unit")
    return {
        "experiment_ids": sorted(row["id"] for row in selection),
        "business_units": units,
        "hours": hours,
        "cost_usd": f"{Decimal(cents) / 100:.2f}",
        "score_units": sum(row["score_units"] for row in selection),
        "unused_hours": limits["hours"] - hours,
        "unspent_usd": f"{Decimal(limits['cost_cents'] - cents) / 100:.2f}",
        "feasible": not violations,
        "violations": violations,
    }


def analyze(rows, capacity):
    candidates, limits = normalize(rows, capacity)
    best_key, best = None, []
    feasible_count = 0
    for size in range(min(limits["active_businesses"], len(candidates)) + 1):
        for selection in itertools.combinations(candidates, size):
            if len({row["unit"] for row in selection}) != size:
                continue
            hours = sum(row["hours"] for row in selection)
            cost = sum(row["cost_cents"] for row in selection)
            if hours > limits["hours"] or cost > limits["cost_cents"]:
                continue
            feasible_count += 1
            score = sum(row["score_units"] for row in selection)
            key = (-score, cost, hours, tuple(row["id"] for row in selection))
            if best_key is None or key < best_key:
                best_key, best = key, selection
    return {
        "classification": "SYNTHETIC",
        "artifact_kind": "reference-analysis-not-approved",
        "objective": "(3 * learning_points + 2 * reuse_points) * confidence_pct; not profit",
        "limits": limits,
        "feasible_selections": feasible_count,
        "worksheet": summarize([row for row in candidates if row["selected"]], limits),
        "recommendation": summarize(best, limits),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worksheet", type=Path)
    parser.add_argument("capacity", type=Path)
    args = parser.parse_args()
    try:
        if args.worksheet.stat().st_size > 100_000 or args.capacity.stat().st_size > 20_000:
            raise ValueError("input exceeds reference size limit")
        with args.worksheet.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        result = analyze(rows, json.loads(args.capacity.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
