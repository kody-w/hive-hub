"""Original offline two-capacity packing reference; not physical fit or safety."""

import argparse
import copy
import csv
import json
import re
from fractions import Fraction
from pathlib import Path

ALGORITHMS = ("input-first-fit", "dominant-first-fit", "volume-first-fit")


def whole(value, low, high, label):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"{label} must be a whole number")
    result = int(value)
    if not low <= result <= high:
        raise ValueError(f"{label} outside {low}..{high}")
    return result


def identifier(value, label):
    if not isinstance(value, str) or len(value) > 60 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError(f"invalid {label}")
    return value


def capacities(capacity):
    return (
        whole(capacity["volume_units"], 1, 10000, "volume capacity"),
        whole(capacity["weight_units"], 1, 10000, "weight capacity"),
    )


def validate_items(items, capacity):
    volume_limit, weight_limit = capacities(capacity)
    if not isinstance(items, list) or len(items) > 60:
        raise ValueError("at most 60 item instances per scenario")
    seen = set()
    for item in items:
        identity = identifier(item["id"], "item ID")
        if identity in seen:
            raise ValueError("duplicate item ID")
        seen.add(identity)
        if type(item["volume"]) is not int or type(item["weight"]) is not int:
            raise ValueError("item loads must be integer values")
        if not 1 <= item["volume"] <= volume_limit or not 1 <= item["weight"] <= weight_limit:
            raise ValueError("item individually exceeds capacity or is nonpositive")


def ordered_items(items, capacity, algorithm):
    if algorithm not in ALGORITHMS:
        raise ValueError("unknown algorithm")
    if algorithm == "input-first-fit":
        return list(items)
    if algorithm == "volume-first-fit":
        return sorted(items, key=lambda item: (-item["volume"], -item["weight"], item["id"]))
    volume_limit, weight_limit = capacities(capacity)
    return sorted(items, key=lambda item: (
        -max(Fraction(item["volume"], volume_limit), Fraction(item["weight"], weight_limit)),
        -(Fraction(item["volume"], volume_limit) + Fraction(item["weight"], weight_limit)),
        item["id"],
    ))


def pack(items, capacity, algorithm="dominant-first-fit"):
    validate_items(items, capacity)
    volume_limit, weight_limit = capacities(capacity)
    bins = []
    for item in ordered_items(items, capacity, algorithm):
        target = next((bin_ for bin_ in bins if bin_["volume_used"] + item["volume"] <= volume_limit and bin_["weight_used"] + item["weight"] <= weight_limit), None)
        if target is None:
            target = {"items": [], "volume_used": 0, "weight_used": 0}
            bins.append(target)
        target["items"].append(item["id"])
        target["volume_used"] += item["volume"]
        target["weight_used"] += item["weight"]
    verify(items, bins, capacity)
    return bins


def verify(items, bins, capacity):
    validate_items(items, capacity)
    volume_limit, weight_limit = capacities(capacity)
    by_id = {item["id"]: item for item in items}
    observed = []
    for bin_ in bins:
        if not bin_["items"] or any(identity not in by_id for identity in bin_["items"]):
            raise ValueError("empty bin or unknown item")
        volume = sum(by_id[identity]["volume"] for identity in bin_["items"])
        weight = sum(by_id[identity]["weight"] for identity in bin_["items"])
        if volume != bin_["volume_used"] or weight != bin_["weight_used"]:
            raise ValueError("reported load disagrees with item loads")
        if volume > volume_limit or weight > weight_limit:
            raise ValueError("bin exceeds capacity")
        observed.extend(bin_["items"])
    if sorted(observed) != sorted(by_id):
        raise ValueError("items missing or repeated")
    return True


def lower_bound(items, capacity):
    validate_items(items, capacity)
    volume_limit, weight_limit = capacities(capacity)
    return max(
        (sum(item["volume"] for item in items) + volume_limit - 1) // volume_limit,
        (sum(item["weight"] for item in items) + weight_limit - 1) // weight_limit,
    )


def exact_minimum(items, capacity, max_items=None, node_limit=None):
    validate_items(items, capacity)
    max_items = whole(capacity["exact_item_limit"] if max_items is None else max_items, 1, 12, "exact item limit")
    node_limit = whole(capacity["exact_node_limit"] if node_limit is None else node_limit, 1, 50000, "exact node limit")
    best = min((pack(items, capacity, algorithm) for algorithm in ALGORITHMS), key=len)
    bound = lower_bound(items, capacity)
    if len(best) == bound:
        return {"best_count": len(best), "lower_bound": bound, "proven": True, "method": "lower-bound", "nodes": 0}
    if len(items) > max_items:
        return {"best_count": len(best), "lower_bound": bound, "proven": False, "method": "skipped-item-limit", "nodes": 0}
    ordered = ordered_items(items, capacity, "dominant-first-fit")
    volume_limit, weight_limit = capacities(capacity)
    bins, nodes, limited = [], 0, False

    def search(index):
        nonlocal best, nodes, limited
        if len(best) == bound:
            return
        if nodes >= node_limit:
            limited = True
            return
        nodes += 1
        if index == len(ordered):
            if len(bins) < len(best):
                best = copy.deepcopy(bins)
            return
        if len(bins) >= len(best):
            return
        item = ordered[index]
        seen_loads = set()
        for bin_ in bins:
            load = (bin_["volume_used"], bin_["weight_used"])
            if load in seen_loads:
                continue
            seen_loads.add(load)
            if load[0] + item["volume"] <= volume_limit and load[1] + item["weight"] <= weight_limit:
                bin_["items"].append(item["id"])
                bin_["volume_used"] += item["volume"]
                bin_["weight_used"] += item["weight"]
                search(index + 1)
                bin_["items"].pop()
                bin_["volume_used"] -= item["volume"]
                bin_["weight_used"] -= item["weight"]
        if len(bins) + 1 < len(best):
            bins.append({"items": [item["id"]], "volume_used": item["volume"], "weight_used": item["weight"]})
            search(index + 1)
            bins.pop()

    search(0)
    verify(items, best, capacity)
    proven = not limited or len(best) == bound
    return {
        "best_count": len(best), "lower_bound": bound, "proven": proven,
        "method": "bounded-search" if proven else "node-limit-unproven", "nodes": nodes,
    }


def load_problem(data_dir):
    data_dir = Path(data_dir)
    csv_path, capacity_path = data_dir / "items.csv", data_dir / "capacity.json"
    if csv_path.stat().st_size > 1_048_576 or capacity_path.stat().st_size > 20000:
        raise ValueError("reference input exceeds size limit")
    capacity = json.loads(capacity_path.read_text(encoding="utf-8"))
    capacities(capacity)
    if capacity["classification"] != "SYNTHETIC":
        raise ValueError("capacity must be explicitly SYNTHETIC")
    item_limit = whole(capacity["max_items_per_scenario"], 1, 60, "scenario item limit")
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    if not rows or len(rows) > 1000:
        raise ValueError("supply 1..1000 item-type rows")
    scenarios, seen = {}, set()
    for row in rows:
        if None in row or any(value is None for value in row.values()) or row["classification"] != "SYNTHETIC":
            raise ValueError("ragged or non-synthetic item row")
        scenario, sku = identifier(row["scenario"], "scenario"), identifier(row["sku"], "SKU")
        if (scenario, sku) in seen:
            raise ValueError("duplicate scenario/SKU")
        seen.add((scenario, sku))
        count = whole(row["count"], 1, 20, "count")
        volume = whole(row["volume-units"], 1, 10000, "volume units")
        weight = whole(row["weight-units"], 1, 10000, "weight units")
        expanded = scenarios.setdefault(scenario, [])
        expanded.extend({"id": f"{sku}-{index:02d}", "volume": volume, "weight": weight} for index in range(1, count + 1))
        if len(expanded) > item_limit:
            raise ValueError("scenario exceeds expanded item limit")
    for items in scenarios.values():
        validate_items(items, capacity)
    return scenarios, capacity


def analyze(data_dir, exact=False):
    scenarios, capacity = load_problem(data_dir)
    results = []
    for scenario, items in sorted(scenarios.items()):
        bound = lower_bound(items, capacity)
        methods = {}
        for algorithm in ALGORITHMS:
            bins = pack(items, capacity, algorithm)
            methods[algorithm] = {"bin_count": len(bins), "gap_to_lower_bound": len(bins) - bound, "bins": bins}
        row = {"scenario": scenario, "item_count": len(items), "lower_bound": bound, "algorithms": methods}
        if exact:
            row["model_proof"] = exact_minimum(items, capacity)
        results.append(row)
    return {
        "classification": "SYNTHETIC", "artifact_kind": "scalar-model-reference-not-physical-validation",
        "capacity": {"volume_units": capacity["volume_units"], "weight_units": capacity["weight_units"]},
        "scenarios": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--exact-small", action="store_true")
    args = parser.parse_args()
    try:
        result = analyze(args.data_dir, args.exact_small)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
