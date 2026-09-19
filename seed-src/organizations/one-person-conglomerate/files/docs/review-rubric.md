# Review rubric

**SYNTHETIC planning model.** Ordinal inputs are intentionally inspectable.

`score_units = (3 × learning_points + 2 × reuse_points) × confidence_pct`.
Learning and reuse are integers 1–5; confidence is an integer 0–100 expressing
a subjective planning belief, not a calibrated probability. Scores are
dimensionless. Monetary amounts have at most two decimal places; hours are
whole founder-hours. Zero-cost experiments are allowed, zero-hour ones are not.
The reference refuses unlabeled/non-synthetic planning inputs and individual
money values above USD 1 billion rather than silently relabeling or overflowing.

The search selects at most one experiment per unit, at most three active
units, and never exceeds the post-reserve limits. It maximizes score, then
prefers lower cost, fewer hours, and lexically earlier experiment IDs. Empty
selection is feasible. Candidate counts above 18 are refused rather than
silently approximated. No coupling, fatigue, correlation, or switching cost
is inferred. Finance should explicitly override weak modeling assumptions.

## Evidence levels

- **Input assumption:** a worksheet estimate or synthetic observation.
- **Artifact evidence:** an actual local test result with command and inputs.
- **Field evidence:** a later consented observation; absent from this seed.
- **Business evidence:** real authorized operating results; absent here.

For the CSV tool, review row numbers, finding codes, and whether input bytes
remain unchanged. It never echoes cell values into findings, repairs files,
executes spreadsheet formulas, or judges whether an amount is financially
correct. Formula detection is conservative: negative numbers and some ordinary
labels may be flagged. Input is limited to 1 MiB and 10,000 records. Binary,
invalid UTF-8, oversized, and malformed CSV are refused.

For an owner decision, require a named assumption for every score change, an
active/parked disposition for all five units, reserves intact, and an explicit
human approval boundary. Passing arithmetic or tool tests does not pass the
business hypothesis.
