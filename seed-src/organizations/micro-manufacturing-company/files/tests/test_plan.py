"""Tests for the authored offline mathematical reference; no fabrication."""
import importlib.util
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("caddy_plan", ROOT / "tools/plan.py")
PLAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.params = PLAN.read_json("design/parameters.json")
        self.dimensions = self.params["dimensions"]

    def test_exact_geometry_and_nominal_fit(self):
        geo = PLAN.geometry(self.dimensions, self.params["material_density_g_cm3"])
        self.assertEqual(geo["tray_volume_mm3"], Decimal("101676"))
        self.assertEqual(geo["insert_volume_mm3"], Decimal("20640"))
        self.assertEqual(geo["solid_mass_g"], Decimal("151.67184"))
        self.assertEqual((geo["tray_inner_width_mm"], geo["tray_inner_depth_mm"]), (174, 94))
        self.assertEqual((geo["insert_width_mm"], geo["insert_depth_mm"]), (171, 91))
        self.assertEqual(geo["nominal_side_clearance_mm"], Decimal("1.5"))

    def test_baseline_economics_and_rounding(self):
        report = PLAN.make_report()
        self.assertEqual(report["economics"]["unit_cost_display_usd"], "7.61")
        self.assertEqual(report["economics"]["batch_cost_usd"], "152.13")
        self.assertNotEqual(Decimal("7.61") * 20, Decimal(report["economics"]["batch_cost_usd"]))
        self.assertFalse(report["manufactured"])
        self.assertEqual(report["external_effects"], [])

    def test_width_change_blocks_pack_and_increases_mass(self):
        baseline, proposed = PLAN.make_report(), PLAN.make_report("196")
        self.assertTrue(baseline["packing"]["envelope_pass"])
        self.assertFalse(proposed["packing"]["envelope_pass"])
        self.assertFalse(proposed["packing"]["checks"]["width"])
        self.assertEqual(proposed["packing"]["required_mm"]["width"], 200)
        self.assertGreater(proposed["geometry"]["solid_mass_g"], baseline["geometry"]["solid_mass_g"])

    def test_synthetic_inspection_rejection_cases(self):
        report = PLAN.make_report()["baseline_sample_exercise"]
        self.assertEqual((report["passes"], report["rejects"]), (3, 2))
        self.assertEqual(report["rows"][2]["failed_features"], ["tray_width_mm"])
        self.assertEqual(report["rows"][3]["failed_features"], ["side_clearance_mm"])

    def test_invalid_geometry_is_rejected(self):
        for change in ({"width": 10}, {"width": 401}, {"floor": 0}, {"clearance": -1}, {"insert_height": 80}, {"rib": 0}, {"depth": "NaN"}, {"height": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                PLAN.geometry({**self.dimensions, **change}, "1.24")

    def test_bom_quantities_cannot_silently_drift(self):
        rows = PLAN.read_csv("data/bom.csv")
        PLAN.validate_bom(rows)
        with self.assertRaises(ValueError):
            PLAN.validate_bom([{**rows[0], "quantity": "2"}, rows[1]])

    def test_invalid_cost_assumptions(self):
        rows = PLAN.read_csv("data/cost-assumptions.csv")
        for change in ({"key": "scrap_fraction", "value": "1"}, {"key": "feedstock_usd_per_kg", "value": "-2"}, {"key": "feedstock_usd_per_kg", "value": "Infinity"}):
            modified = [{**row, "value": change["value"]} if row["key"] == change["key"] else row for row in rows]
            with self.subTest(change=change), self.assertRaises(ValueError):
                PLAN.costs_from_rows(modified)

    def test_duplicate_samples_and_limits_fail(self):
        samples, limits = PLAN.read_csv("quality/inspection-samples.csv"), PLAN.read_csv("quality/dimensions.csv")
        with self.assertRaises(ValueError):
            PLAN.inspect_samples(samples + [samples[0]], limits)
        with self.assertRaises(ValueError):
            PLAN.inspect_samples(samples, limits + [limits[0]])

    def test_scad_parameters_match_and_override_is_inert(self):
        original = (ROOT / "design/desk-caddy.scad").read_text(encoding="utf-8")
        self.assertEqual(PLAN.scad_source(self.dimensions), original)
        changed = PLAN.scad_source({**self.dimensions, "width": 196})
        self.assertIn("width = 196;", changed)
        self.assertEqual((ROOT / "design/desk-caddy.scad").read_text(encoding="utf-8"), original)

    def test_svg_outputs_are_parseable_and_local(self):
        for text in ((ROOT / "design/desk-caddy.svg").read_text(encoding="utf-8"), PLAN.svg_source(self.dimensions), PLAN.svg_source({**self.dimensions, "width": 196})):
            svg = ET.fromstring(text)
            self.assertEqual(svg.tag, "{http://www.w3.org/2000/svg}svg")
            self.assertNotIn("<script", text)
            self.assertNotIn("href=", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
