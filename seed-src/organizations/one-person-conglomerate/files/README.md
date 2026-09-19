# The One-Person Conglomerate

This is an inert organization seed, not an activated business or a profit
simulation. All portfolio data is **SYNTHETIC**. Five business-unit workspaces
share executive, research, finance, engineering, and go-to-market functions.
Only three units may consume founder attention in the reference cycle.

## Use the original offline tools

From this package's `files/` directory, with Python 3.10 or newer:

```sh
python3 -I -B reference/test_allocation.py
python3 -I -B reference/allocation.py data/allocation-worksheet.csv data/capacity.json
python3 -I -B reference/test_csv_guard.py
python3 -I -B reference/csv_guard.py data/csv-intake.csv --columns classification invoice-id amount-usd --key invoice-id
```

No installations, server, network, credentials, or writes are required. The
last command intentionally exits **1**: the supplied synthetic CSV repeats
`sample-003`. This is an intake finding, not a broken tool. Exit 2 means invalid
arguments or an unreadable input. Tests construct tiny input strings in memory.

The allocation search examines at most 18 candidate rows. Its objective is a
subjective learning/reuse score, **not expected profit**. The supplied worksheet
selects 19 hours and USD 90; the mathematical recommendation selects 21 hours
and USD 90 across Ledgerleaf, Quietbench, and Tinylesson. Neither is approved.
The score can be wrong even when the arithmetic is right.

Start with `docs/charter.md`, the actual editable worksheet, and the pending
blueprint tasks. Review business-unit proposals before accepting optimization.
The CSV preflight utility is a usable reference artifact that one unit could
develop; the other four businesses have concrete starter briefs, not invented
products or customers. Source examples and test runs are not completed
organization tasks. External research, publication, payment, and membership
remain separately approval-gated.
