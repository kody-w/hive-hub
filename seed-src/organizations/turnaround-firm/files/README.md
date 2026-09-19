# Cedarline Desk — turnaround seed

**SYNTHETIC** business, transactions, subscriptions, payables, and support
records. No customer is real; no live money, account, trade, deployment,
message, savings, or profit is represented.

Cedarline Desk is a fictional subscription pick-ticket scheduling business.
Receipts decline while refunds and hosting allocations rise. A tiny, actual
authored software defect alphabetizes support severity, so low-priority items
receive the first four dispatch slots. `product/dispatch.py` intentionally
preserves that defective baseline. It is **not** a production-ready scheduler.

## Run the working analysis and recovery simulation

From `files/`, using Python 3 and stdlib only:

```text
python3 -I -B tools/recovery.py
python3 -I -B tools/recovery.py --section cash
python3 -I -B tools/recovery.py --section queue
python3 -I -B tools/recovery.py --capacity-minutes 0 --section queue
python3 -I -B tests/test_recovery.py
```

The utility reads the exact included files, executes only the original local
dispatcher fixture, and prints a report. It writes nothing, dispatches nothing,
and performs no financial/customer/network operation. The candidate queue is a
reference policy simulation, not an installed fix.

## Reproducible diagnosis

- Opening cash USD 52000 + receipts USD 48500 − payments USD 68100 =
  closing cash USD 32400. Fifteen ledger entries cover July–September 2026.
- Monthly cash changes: −4000, −6600, −9000. The synthetic subscription
  cohorts reconcile to receipts of 18000, 16000, and 14500 respectively.
- Reserve USD 5500 in **incremental prior-period catch-up obligations**,
  not already paid or included in recurring scenario rows. USD 26900 remains.
- Repeating September's USD 9000 monthly burn gives 89.7 modeled days to zero
  after that reserve, or 49.7 days to a USD 12000 floor. Months mean 30 days.
- The unapproved containment scenario reduces monthly allocations by USD 1700
  and models USD 7300 monthly burn. This is not achieved savings or a forecast.
- Twelve open tickets contain 690 estimated minutes; one blocked urgent ticket
  accounts for 120. The 420-minute simulation selects six eligible tickets
  and leaves all blocked/deferred work visible.

The legacy first four are `ticket-009`, `ticket-002`, `ticket-006`,
`ticket-012`. Correct severity ordering begins `ticket-001`, `ticket-010`,
`ticket-007`, `ticket-011`. With 420 minutes, the non-preemptive fit policy
selects `001, 010, 007, 011, 005, 008`: it skips a 60-minute normal ticket
when only 45 minutes remain. That trade-off must be explicitly reviewed.

## Organization handoff and limits

Five teams join diagnosis to a five-day sprint plan, with separate 360-minute
engineering and 420-minute support budgets. All deliverables are future work.
The cash model is not a full financial statement, accounting opinion, or
solvency assessment: it omits taxes, financing, receivables, deferred revenue,
and unknown liabilities. In this authored fixture only, each month's plan
billings were collected in that month. Runway is mechanical scenario arithmetic,
not a guarantee. Support estimates and affected-account counts are synthetic;
counts may overlap and cannot be summed as unique customers.

External effects, contracts, spending, customer messages, refunds, cost changes,
production deployment, and publication require separate owner approval.
