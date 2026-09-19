# Stackline desk caddy — micro-manufacturing seed

All business, cost, client, and sample-measurement data is **SYNTHETIC**. No
supplier was contacted, no parts purchased, and nothing was made or shipped.
This is a non-safety-critical desk organizer design/planning case, not a
manufacturing qualification or machinery guide.

## Usable reference

`design/desk-caddy.scad` is original parametric OpenSCAD source with `assembly`,
`tray`, and `insert` part selectors. `design/desk-caddy.svg` is a dimensioned
top-view illustration. The tray is 180 × 100 × 32 mm; its removable ladder
insert separates three loose-item bays without glue, fasteners, or purchased
components. It is not a cutting/toolpath file or a precision-fixture design.

From `files/`, with Python 3 and no dependencies:

```text
python3 -I -B tools/plan.py
python3 -I -B tools/plan.py --width-mm 196
python3 -I -B tools/plan.py --format svg
python3 -I -B tools/plan.py --width-mm 196 --format scad
python3 -I -B tests/test_plan.py
```

Commands read only these local reference files and print to stdout; they do not
write, invoke CAD software, fabricate, order, or ship. SCAD rendering is optional
if an owner already has a suitable CAD tool; the Python tests do not claim to
have run that renderer.

The solid-volume model gives 101676 mm³ for the tray and 20640 mm³ for the
insert. At the assumed 1.24 g/cm³, total modeled mass is 151.67184 g. With the
included hypothetical yield and cost inputs, a unit displays USD 7.61 and
twenty units aggregate to USD 152.13. Totals are rounded **after** aggregation.
This is not a real quote or achieved margin.

The 196 mm width change fails the current 192 mm internal packing width:
196 + 2 × 2 = 200 mm. Baseline synthetic sample rows 01, 02, and 05 meet the
specified checks; 03 and 04 do not. These are authored numbers, not inspection
records from a manufactured batch.

## Limits and handoff

Seven teams trace one change from requirements through geometry, assumptions,
dry-fit planning, dimensional quality, logistics, and finance. Start at
`freeze-desk-use`. Every deliverable is future work.

The model ignores process shrinkage, porosity, warping, structural strength,
finish, production labor variability, freight, tax, and certification.
Nominal clearance is not a guarantee of fit. No material is approved for food,
electrical, medical, child-safety, thermal, or load-bearing use. Physical work,
process selection, purchases, publication, and shipment require separate owner
review and approval. No RAPP identity or runtime is created by this content.
