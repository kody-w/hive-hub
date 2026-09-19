# Exact reference acceptance cases

All amounts and account scenarios are **SYNTHETIC USD**. These are expected
reference results, not invoices, approvals, or completed quality work.

| Quote | Expected total | State | Principal case |
|---|---:|---|---|
| q-101 | 268.21 | ready-for-human-approval | 250 gross, 12.50 discount, 17.81 line tax, 12 shipping, 0.90 shipping tax |
| q-102 | 116.10 | needs-review | 920 open balance + 116.10 exceeds 1000 limit |
| q-103 | 208.55 | needs-review | 8% discount exceeds standard tier's 5% cap |
| q-104 | 935.16 | needs-review | Inactive account and 60 requested days versus 30 approved |
| q-105 | null | needs-data | Missing PO and unknown tax code |
| q-106 | 10.16 | ready-for-human-approval | 0.15 taxable line rounds tax to 0.01; 10.00 exempt line |
| q-107 | null | needs-data | Quantity -1 is invalid for this quote-only model |
| q-108 | 107.50 | needs-review | 45 requested days versus 30 approved |

Check the JSON fixture for exact sorted reason codes. Tests also check
determinism, no in-memory mutation, unknown accounts, duplicate keys, bounds,
and policy boundary behavior. The sample's q-104 discount net is 849.915 before
rounding and **849.92** after half-up rounding. Floating-point approximations
must not decide the cent.

Blocking data errors suppress totals for the entire quote, even when some
lines could be calculated. Policy flags may still appear alongside a data
blocker. A clean reference comparison only establishes behavior on specified
inputs; it does not validate actual commercial, tax, or legal policy.
