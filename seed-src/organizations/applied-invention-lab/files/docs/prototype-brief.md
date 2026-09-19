# Operator-readable assignment prototype

**SYNTHETIC model-only reference. No physical packing has been performed.**

Use `order-trap` first because the difference between three input-order bins
and two decreasing-load bins is inspectable. A proposed printable layout has:

- Scenario label, algorithm, dataset provenance, and a model-only warning.
- One numbered section per tote.
- Exact local item IDs, item labels, volume and weight proxy totals.
- Remaining capacity in both dimensions, shown as numbers and text.
- An explicit “check mock geometry before use” instruction and a way to
  record an operator's correction without overwriting the model result.

For the two-bin decreasing-load reference, each bin should pair one
six-volume/three-weight core with one four-volume/two-weight filler. That is
volume 10 and weight 5 per bin. It proves scalar feasibility, not shape fit.

The later mock study should use empty or lightweight paper/foam
representations. Review whether labels are understandable, each item can be
found, and modeled pairings make geometric sense. Do not infer safe lifting,
container strength, shipment suitability, or actual load limits from these
abstract units. No physical observation values are supplied in this seed.
