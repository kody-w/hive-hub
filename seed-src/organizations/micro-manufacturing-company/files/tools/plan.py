"""Offline, read-only desk-caddy geometry, cost, inspection and packing planner."""
import argparse
import csv
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = ("width", "depth", "height", "wall", "floor", "clearance", "insert_height", "rib")
COST_KEYS = {
    "feedstock_usd_per_kg", "scrap_fraction", "bench_minutes_per_kit",
    "bench_usd_per_hour", "packaging_usd_per_kit", "overhead_usd_per_kit",
    "scenario_price_usd_per_kit"
}


def dec(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a dimension or cost")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Finite numeric values required")
    return number


def read_json(relative):
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if value.get("classification") != "SYNTHETIC":
        raise ValueError("Only SYNTHETIC reference inputs are supported")
    return value


def read_csv(relative):
    with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(row.get("classification") != "SYNTHETIC" for row in rows):
        raise ValueError("Expected nonempty SYNTHETIC data")
    return rows


def geometry(dimensions, density):
    if set(dimensions) != set(PARAMETERS):
        raise ValueError("Unexpected or missing dimension")
    p = {key: dec(value) for key, value in dimensions.items()}
    w, d, h, wall, floor, gap, ih, rib = (p[key] for key in PARAMETERS)
    density = dec(density)
    if not (wall >= 2 and floor >= 2 and gap >= Decimal("0.5") and rib >= 1 and density > 0):
        raise ValueError("Invalid wall, floor, clearance, rib, or density")
    if not (2 * wall + 2 * gap + 6 * rib < w <= 400 and 2 * wall + 2 * gap + 2 * rib < d <= 300):
        raise ValueError("Tray dimensions cannot contain the insert")
    if not (floor < h <= 100 and 0 < ih <= h - floor):
        raise ValueError("Insert must remain below the tray rim")
    inner_w, inner_d = w - 2 * wall, d - 2 * wall
    iw, inside_d = inner_w - 2 * gap, inner_d - 2 * gap
    tray = w * d * h - inner_w * inner_d * (h - floor)
    insert = (2 * iw * rib + 2 * rib * (inside_d - 2 * rib)) * ih
    return {
        "tray_inner_width_mm": inner_w, "tray_inner_depth_mm": inner_d,
        "insert_width_mm": iw, "insert_depth_mm": inside_d,
        "nominal_side_clearance_mm": gap,
        "tray_volume_mm3": tray, "insert_volume_mm3": insert,
        "solid_mass_g": (tray + insert) / 1000 * density
    }


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def costs_from_rows(rows):
    costs = {}
    for row in rows:
        if row["key"] in costs or row["key"] not in COST_KEYS:
            raise ValueError("Duplicate or unknown cost assumption")
        costs[row["key"]] = dec(row["value"])
    if set(costs) != COST_KEYS or any(value < 0 for value in costs.values()):
        raise ValueError("Missing or negative cost assumption")
    if costs["scrap_fraction"] >= 1:
        raise ValueError("Scrap fraction must be below one")
    return costs


def economics(geo, costs, quantity):
    if type(quantity) is not int or not 1 <= quantity <= 10000:
        raise ValueError("Bounded positive integer quantity required")
    material = geo["solid_mass_g"] / 1000 * costs["feedstock_usd_per_kg"] / (1 - costs["scrap_fraction"])
    handling = costs["bench_minutes_per_kit"] / 60 * costs["bench_usd_per_hour"]
    unit = material + handling + costs["packaging_usd_per_kit"] + costs["overhead_usd_per_kit"]
    return {
        "classification": "SYNTHETIC",
        "material_usd_per_kit": money(material), "handling_usd_per_kit": money(handling),
        "unit_cost_unrounded_usd": str(unit), "unit_cost_display_usd": money(unit),
        "quantity": quantity, "batch_cost_usd": money(unit * quantity),
        "hypothetical_unit_contribution_usd": money(costs["scenario_price_usd_per_kit"] - unit),
        "basis": "Solid-volume/yield/handling scenario; excludes fabrication machine time, freight and tax. No actual sales, profit or quote."
    }


def packing(dimensions, geo, spec):
    pad = dec(spec["padding_each_side_mm"])
    packaging_mass = dec(spec["packaging_mass_g"])
    maximum_mass = dec(spec["maximum_modeled_packed_mass_g"])
    if pad < 0 or packaging_mass < 0 or maximum_mass <= 0:
        raise ValueError("Invalid packing assumption")
    needed = {axis: dec(dimensions[axis]) + 2 * pad for axis in ("width", "depth", "height")}
    limits = {axis: dec(spec["internal_mm"][axis]) for axis in needed}
    if any(value <= 0 for value in limits.values()):
        raise ValueError("Invalid packing envelope")
    checks = {axis: needed[axis] <= limits[axis] for axis in needed}
    mass = geo["solid_mass_g"] + packaging_mass
    checks["mass"] = mass <= maximum_mass
    return {"required_mm": needed, "packed_mass_g": mass, "checks": checks, "envelope_pass": all(checks.values()), "transit_tested": False}


def inspect_samples(samples, limits):
    limit_map = {}
    for row in limits:
        key = row["feature_id"]
        if key in limit_map:
            raise ValueError("Duplicate dimensional feature")
        low, nominal, high = dec(row["lower_mm"]), dec(row["nominal_mm"]), dec(row["upper_mm"])
        if not 0 <= low <= nominal <= high:
            raise ValueError("Invalid dimensional limits")
        limit_map[key] = (low, high)
    if set(limit_map) != {"tray_width_mm", "tray_depth_mm", "tray_height_mm", "side_clearance_mm"}:
        raise ValueError("Incomplete reference inspection limits")
    results, ids = [], set()
    for row in samples:
        if row["sample_id"] in ids or row["classification"] != "SYNTHETIC" or row["edge_pass"] not in ("0", "1"):
            raise ValueError("Invalid synthetic inspection sample")
        ids.add(row["sample_id"])
        measured = {key: dec(row[key]) for key in ("tray_width_mm", "tray_depth_mm", "tray_height_mm", "inner_width_mm", "insert_width_mm")}
        if any(value <= 0 for value in measured.values()):
            raise ValueError("Measurements must be positive")
        measured["side_clearance_mm"] = (measured["inner_width_mm"] - measured["insert_width_mm"]) / 2
        failures = [key for key, (low, high) in limit_map.items() if not low <= measured[key] <= high]
        if row["edge_pass"] == "0":
            failures.append("visible_edges")
        results.append({"sample_id": row["sample_id"], "pass": not failures, "failed_features": failures, "side_clearance_mm": measured["side_clearance_mm"]})
    return results


def validate_bom(rows):
    expected = {"tray": "tray_volume_mm3", "insert": "insert_volume_mm3"}
    if len(rows) != 2 or {row["part_id"] for row in rows} != set(expected):
        raise ValueError("Reference requires exactly one tray and one insert")
    for row in rows:
        if row["quantity"] != "1" or row["geometry_key"] != expected[row["part_id"]] or row["source_selector"] != row["part_id"]:
            raise ValueError("BOM and geometry disagree")


def make_report(width=None):
    parameters = read_json("design/parameters.json")
    dimensions = dict(parameters["dimensions"])
    if width is not None:
        dimensions["width"] = dec(width)
    geo = geometry(dimensions, parameters["material_density_g_cm3"])
    validate_bom(read_csv("data/bom.csv"))
    costs = costs_from_rows(read_csv("data/cost-assumptions.csv"))
    samples = inspect_samples(read_csv("quality/inspection-samples.csv"), read_csv("quality/dimensions.csv"))
    return {
        "classification": "SYNTHETIC", "dimensions_mm": dimensions, "geometry": geo,
        "economics": economics(geo, costs, read_json("case/brief.json")["planning_quantity"]),
        "packing": packing(dimensions, geo, read_json("ops/pack-spec.json")),
        "baseline_sample_exercise": {"passes": sum(row["pass"] for row in samples), "rejects": sum(not row["pass"] for row in samples), "rows": samples},
        "inspection_scope": "Authored baseline dimensions only; does not validate changed geometry or any physical object.",
        "external_effects": [], "manufactured": False
    }


def scad_source(dimensions):
    geometry(dimensions, 1)
    source = (ROOT / "design/desk-caddy.scad").read_text(encoding="utf-8")
    for key in PARAMETERS:
        source, count = re.subn(rf"^{key} = [0-9.]+;$", f"{key} = {dec(dimensions[key])};", source, flags=re.MULTILINE)
        if count != 1:
            raise ValueError("SCAD parameter source is inconsistent")
    return source


def svg_source(dimensions):
    geo = geometry(dimensions, 1)
    w, d, wall, gap, rib = (dec(dimensions[key]) for key in ("width", "depth", "wall", "clearance", "rib"))
    iw, inside_d = geo["insert_width_mm"], geo["insert_depth_mm"]
    bars = "".join(f'<rect x="{iw * fraction / 3 - rib / 2}" y="{rib}" width="{rib}" height="{inside_d - 2 * rib}"/>' for fraction in (1, 2))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w+40} {d+60}">
<title>Original Stackline {w} by {d} mm top-view scenario</title>
<rect width="100%" height="100%" fill="#f4f1e9"/>
<g transform="translate(20 20)" stroke="#233f42" stroke-width=".5">
<rect width="{w}" height="{d}" fill="#bcc8c7"/>
<rect x="{wall}" y="{wall}" width="{w-2*wall}" height="{d-2*wall}" fill="#f4f1e9"/>
<g transform="translate({wall+gap} {wall+gap})" fill="#397c78">
<rect width="{iw}" height="{rib}"/><rect y="{inside_d-rib}" width="{iw}" height="{rib}"/>{bars}</g></g>
<text x="20" y="{d+35}" font-family="sans-serif" font-size="5">{w} × {d} mm; gap {gap} mm</text>
<text x="20" y="{d+45}" font-family="sans-serif" font-size="4">SYNTHETIC design study; not a cutting file or manufactured item.</text></svg>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width-mm", help="Hypothetical width override; leaves reference files unchanged")
    parser.add_argument("--format", choices=("json", "svg", "scad"), default="json")
    args = parser.parse_args()
    report = make_report(args.width_mm)
    if args.format == "scad":
        print(scad_source(report["dimensions_mm"]), end="")
    elif args.format == "svg":
        print(svg_source(report["dimensions_mm"]))
    else:
        print(json.dumps(report, indent=2, sort_keys=True, default=str, allow_nan=False))


if __name__ == "__main__":
    main()
