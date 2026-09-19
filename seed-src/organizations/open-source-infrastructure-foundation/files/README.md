# The Open-Source Infrastructure Foundation

**Original deliberately imperfect reference project: Line Ledger.**
All work-item events are **SYNTHETIC** inert data. No third-party source,
private repository content, real issue tracker, credentials, or hostile
host-affecting fixture is included.

Line Ledger reduces small JSONL open/close events into a work-item summary.
The reference intentionally has two ordinary logic defects:

1. Identical event IDs are counted again instead of deduplicated.
2. Arrival order determines final state instead of event minute / event ID.

These are starter repair tasks. They have **not** been fixed in this source
package, and this reference is **not release-ready**.

## Reproduce locally

From `files/`, using Python 3.10 or newer:

```sh
python3 -I -B reference/test_baseline.py
python3 -I -B reference/line_ledger.py data/events-clean.jsonl
python3 -I -B reference/check_acceptance.py --characterize
python3 -I -B reference/check_acceptance.py
```

No installs, network, server, subprocesses, or writes are used. The first
three commands should exit 0. The final strict checker intentionally exits
**1**, with one passing case and two failing cases. Characterization confirms
the supplied defects; it is not a substitute for strict acceptance.

The seven team workspaces own scope, reproduction, two sequential patches,
boundary review, contributor docs, candidate acceptance, and approval-gated
release planning. `docs/contract.md` defines desired behavior;
`data/expected-contract.json` must not be weakened to hide the defects.
Reference baseline tests characterize the original; a future fixed candidate
must update those characterization assertions to the corrected behavior.

All source and fixtures were authored for this seed. The short permission
notice applies to these original materials, not to any external project.
Nothing grants publication, signing, identity, membership, or repository
authority.
