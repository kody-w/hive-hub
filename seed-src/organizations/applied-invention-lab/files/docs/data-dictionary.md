# Original dataset and units

**SYNTHETIC — not measured physical data.**

`items.csv` has 11 item-type rows, expanding to 29 instances:
`order-trap` 4, `weight-trap` 8, `mixed-classroom` 14, `bulky-gaps` 3.

| Field | Meaning |
|---|---|
| classification | Literal SYNTHETIC in this public reference |
| scenario | Independent case; items never cross scenario boundaries |
| sku | Original local item-type label, not a commercial catalog ID |
| count | Positive whole number of instances; at most 20 per row |
| volume-units | Positive integer capacity proxy per instance |
| weight-units | Positive integer second capacity proxy per instance |
| shape-note | Qualitative assumption deliberately not consumed by the scalar solver |

Each instance ID is `sku-01`, `sku-02`, etc.; IDs are local data labels, not
RAPPIDs or any identity credential. SKU uniqueness is enforced within a
scenario. Original source order is meaningful for the input-order baseline.

Every modeled tote has volume capacity 10 and weight capacity 10. No
conversion to liters, mass, allowable lifting weight, or structural capacity
is justified. Items are indivisible in the model, and there are no
compatibility, accessibility, center-of-gravity, geometry, or kit-cohesion
constraints. A shape note exists precisely to expose that missing dimension.

The reader bounds CSV size at 1 MiB, row count at 1,000, and expanded scenario
size at 60. Values must be positive integers; an oversized item fails instead
of being silently forced into a tote. Blank or duplicate keys fail. All
computational labels and quantities are original synthetic seed content.
