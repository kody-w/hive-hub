"""Original seeded paired-permutation study of a synthetic scalar packing model."""

import argparse
import hashlib
import importlib.util
import json
import random
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("tote_pack_experiment", HERE / "tote_pack.py")
packing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packing)


def run(data_dir):
    data_dir = Path(data_dir)
    scenarios, capacity = packing.load_problem(data_dir)
    plan_path = data_dir / "experiment-plan.json"
    if plan_path.stat().st_size > 20000:
        raise ValueError("plan exceeds reference limit")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan["classification"] != "SYNTHETIC" or plan["algorithms"] != list(packing.ALGORITHMS):
        raise ValueError("use the declared synthetic three-algorithm plan")
    repetitions = packing.whole(plan["repetitions"], 1, 100, "repetitions")
    seed = packing.whole(plan["random_seed"], 0, 2**32 - 1, "seed")
    rng = random.Random(seed)
    results = []
    for scenario, items in sorted(scenarios.items()):
        counts = {algorithm: [] for algorithm in packing.ALGORITHMS}
        for _ in range(repetitions):
            permutation = list(items)
            rng.shuffle(permutation)
            for algorithm in packing.ALGORITHMS:
                bins = packing.pack(permutation, capacity, algorithm)
                packing.verify(items, bins, capacity)
                counts[algorithm].append(len(bins))
        results.append({
            "scenario": scenario,
            "item_count": len(items),
            "algorithms": {
                algorithm: {
                    "counts": values, "min": min(values), "max": max(values),
                    "mean": f"{Decimal(sum(values)) / len(values):.3f}",
                } for algorithm, values in counts.items()
            },
        })
    hashes = {
        filename: hashlib.sha256((data_dir / filename).read_bytes()).hexdigest()
        for filename in ("items.csv", "capacity.json", "experiment-plan.json")
    }
    return {
        "classification": "SYNTHETIC",
        "artifact_kind": "computational-experiment-not-physical-or-market-evidence",
        "seed": seed, "repetitions": repetitions, "source_sha256": hashes,
        "pairing": "The same permutation is used across algorithms within each trial.",
        "scenarios": results,
        "limitations": [
            "Abstract capacities do not establish geometric fit or safe handling.",
            "Four authored scenarios are not a sampled real-world population.",
            "Seeded permutation sequences should be compared with runtime version recorded.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.data_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
