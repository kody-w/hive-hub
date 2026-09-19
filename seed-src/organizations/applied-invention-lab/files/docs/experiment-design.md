# Predeclared computational experiment

**SYNTHETIC model study. No physical experiment or user study has occurred.**

## Question and comparison

Does dominant-load decreasing first-fit reduce modeled bin count relative
to input-order first-fit, and where does it regress? Compare all three:

1. `input-first-fit`: place each item in the first feasible bin in supplied
   order, otherwise open a new bin.
2. `dominant-first-fit`: sort by descending maximum normalized load, then
   descending sum of normalized loads, then ascending local item ID.
3. `volume-first-fit`: sort by descending volume, then weight, then item ID.

Each insertion must satisfy both capacity constraints. The deterministic
sorted methods are not novel algorithms and no invention claim is made.

## Fixed experiment plan

Use seed 1729 and 20 permutations per scenario. Within a trial, feed the same
permutation to all three methods. Retain all 240 resulting bin counts
(4 scenarios × 3 methods × 20 trials). Store min, max, and arithmetic mean as
descriptive summaries, not confidence about a real population. Keep the
unshuffled baseline separate from the randomized order experiment.

No trial exclusion is permitted except an invalid input, which stops the
run and must be reported. Do not change capacities, scenario membership, or
the seed after seeing an unfavorable result. Proposed future variations
need a separately versioned plan and side-by-side reporting.

## Bounds and proof

The scalar lower bound is the maximum of the ceiling of total volume divided
by volume capacity and the corresponding weight ratio. Matching a feasible
packing count proves optimal bin count *within this model*. Otherwise an
optional depth-first branch-and-bound search explores at most 12 items and
50,000 nodes. It reports proven, skipped, or node-limit-unproven honestly.
An optimum of this abstraction proves nothing about three-dimensional fit.

## Decision rule

Continue only if the assignment prototype is explainable and at least one
useful computation survives replication. Do not claim universal superiority:
the mixed-classroom baseline is a known counterexample. Before discussing a
practical benefit, run a separately approved mock-fit and comprehension
study. Commercial interviews and spending require their own owner approvals.
