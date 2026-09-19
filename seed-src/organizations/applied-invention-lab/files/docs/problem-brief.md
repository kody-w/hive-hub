# Practical problem brief

**All service descriptions, items, and numbers are SYNTHETIC.**

A fictional library assembles reusable learning kits: blank cards, cloth
squares, soft foam shapes, counters, and lightweight boards. Staff want
packing instructions that are easier to inspect than an opaque bin count.
The initial question is narrow: under two *modeled* capacities, how many
totes do three simple heuristics use, and how sensitive are they to order?

We do not know actual item dimensions, nesting, compression, fragility,
access order, handling limits, setup time, or user preferences. Those gaps
matter: two items that fit aggregate volume can still be impossible to place
geometrically. A better scalar count might produce worse instructions.

## Four deliberately informative scenarios

- **order-trap:** two small fillers precede two larger cores. Input-order
  first-fit uses three bins; decreasing-load methods can pair them in two.
- **weight-trap:** light bulky items and dense small pouches illustrate why
  both constraints must be checked. Volume-first fills two light-panel bins
  with medium boards too early, leaving dense pouches in separate bins: five
  bins versus four for the other supplied baseline orders.
- **mixed-classroom:** five types show that a plausible dominant-load
  heuristic can be worse than the provided order. This unfavorable case is
  deliberately retained.
- **bulky-gaps:** three indivisible six-volume items need three bins even
  though the aggregate lower bound is two. A lower bound is not always the
  answer.

The immediate deliverable is reproducible model evidence and a printable
instruction prototype. Any later study should begin with harmless empty or
lightweight mock materials and owner-approved observation, not actual
shipping, load testing, or safety-critical operation.
