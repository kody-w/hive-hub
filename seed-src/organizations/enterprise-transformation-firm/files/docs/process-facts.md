# Quote-to-cash process fact register

These are **SYNTHETIC facts of the case**, not observations of a real client.

| ID | Current case fact | Design consequence |
|---|---|---|
| pf-intake | Sellers prepare quote headers and line items separately. | Reconcile quote IDs and reject orphan or duplicate keys. |
| pf-po | A PO reference is mandatory before readiness review. | Missing PO is a data blocker, not a policy waiver. |
| pf-credit | Open account balance excludes these sample quotes. | Evaluate each quote independently; do not sum a batch into an approval. |
| pf-round | Billing rounds each net line and its tax to cents, half up. | Rounding the final batch sum is not equivalent. |
| pf-ship | Shipping may be taxable and has a separate rounded tax amount. | Include the header flag and synthetic shipping tax code. |
| pf-review | Discount, account, terms, and credit exceptions go to people. | A calculation may route but must not approve. |
| pf-data | The sample has two incomplete/invalid quotes. | Preserve originals; record proposed corrections separately. |
| pf-lag | A fictional queue snapshot suggests handoffs can span two workdays. | Treat this as a case assumption; collect a real baseline before claims. |

## Field dictionary

All amounts are synthetic USD decimal strings with at most two fractional
digits. Quantities are whole positive units; percentages are in 0–100, not
fractions. Terms are integers from 1–120 days. `yes`/`no` are exact flags.
Tax codes are `standard` (7.5%) and `exempt` (0%) in the reference only.
Unknown tax codes block calculation; the program does not determine tax law.
The public reference refuses non-synthetic or unlabeled input files rather
than relabeling real data as synthetic.

Account credit exposure = existing open balance + this quote's total.
This is neither a credit reservation nor a concurrency-safe credit service.
Multiple simultaneously approved quotes could exceed a limit even if each
isolated example is clean. Inventory availability, exchange rates, returns,
partial fulfillment, credits, promotions, and tax jurisdiction are excluded.

## Proposed state precedence

1. **needs-data:** missing/invalid required fields; totals are null.
2. **needs-review:** calculable but outside a supplied policy.
3. **ready-for-human-approval:** all reference checks clear; still not approved.

A source correction creates a new evaluation; it does not erase the original.
An enterprise adapter would need its own identity, authorization, audit,
idempotency, locking, and rollback design outside this package.
