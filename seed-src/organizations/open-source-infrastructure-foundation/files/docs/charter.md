# Foundation charter

**SYNTHETIC project exercise, original source, no activated organization.**

Maintain a tiny, understandable event reducer rather than inventing a new
distributed runtime. Line Ledger is a pure local data tool; it is not a queue
service, RAPP protocol, signed log, identity system, or source of authority.
Keep its code small enough that contributors can reason about the complete
contract.

## This cycle

- Reproduce two deliberately present defects before repairing anything.
- Correct deduplication first, then stable event ordering.
- Preserve bounded validation, deterministic output, and no input mutation.
- Require strict desired-behavior tests and regression evidence before a
  candidate can be considered for any later release.
- Keep contributor guidance usable while the reference is still failing.

Maintainers own scope and review; triage owns reproducibility; engineering
owns candidate patches; security reviews the inert input boundary; docs own
operator clarity; release owns evidence gates; community owns respectful
intake. These are workspace responsibilities, not created memberships.

No actual repository issue, release, contributor, adoption result, download
count, or public announcement exists in this case. The seed provides original
source work and an honest dependency graph, not fabricated community activity.
