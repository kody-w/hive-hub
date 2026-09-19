# Team and operator handoff contracts

**SYNTHETIC proposed operating model; no accounts or authority are created.**

Discovery hands Architecture a requirement ID, source field, current case
fact, uncertainty, and acceptance case. Architecture hands Engineering a pure
calculation contract and separately documented integration exclusions.
Engineering hands Quality command, input paths, input provenance, full JSON
result, and authored test summary. Quality hands Adoption the observed
classification matrix, not a certificate of enterprise readiness.

## Operator exceptions

| Reason | Proposed role | Minimum handoff | Re-evaluation trigger |
|---|---|---|---|
| missing-po | Seller | Quote ID, missing field, source submission | Authorized PO reference supplied |
| unknown-tax-code | Billing coordinator | Quote/line IDs and unresolved code | Actual policy owner confirms code |
| invalid-quantity | Seller | Original line and validation rule | Authorized corrected positive quantity |
| credit-limit | Credit reviewer | Total, open balance, limit, exposure | Authorized decision or changed inputs |
| discount-policy | Commercial reviewer | Line discount, tier, cap | Authorized revised commercial terms |
| inactive-account | Account owner | Account state and quote ID | Authorized account review |
| terms-policy | Commercial reviewer | Requested and approved days | Authorized revised terms |

Propose one business day to acknowledge an exception and two to resolve or
escalate. These are targets for discussion, not observed SLAs. No role is a
named person; no notification is sent. A review outcome must not be represented
by changing `ready-for-human-approval` to a fabricated authorized state.

The reference CLI reads the explicitly supplied data directory. It never
discovers live systems. Any later connector needs a separately approved plan,
least-privilege scope, concurrency controls, data retention, and a real system
of record. This seed supplies none of those credentials or capabilities.
