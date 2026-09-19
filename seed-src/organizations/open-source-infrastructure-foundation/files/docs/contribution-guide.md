# Contributor repair guide

**Original code and SYNTHETIC fixtures only. No repair is already completed.**

Read the full contract and run baseline tests, characterization, and strict
acceptance before editing. Keep a distinction between:

- `test_baseline.py`: source-reference characterization plus validation tests;
- `check_acceptance.py`: desired contract comparison;
- `--characterize`: verifies that this intentionally failing source still has
  exactly the documented one-pass/two-fail shape.

## Suggested patch boundaries

**Deduplication patch:** preserve `validate_events` conflict detection, then
retain one event per identical event ID. Verify duplicate input does not
change global or per-item counts. Keep the other ordering defect visible
until its own patch is reviewed.

**Ordering patch:** after deduplication, sort by minute and event ID.
Regression tests should include reversed arrival order and equal-minute
open/close events. Keep item output order deterministic.

The blueprint serializes these patches so two teams do not write competing
edits to the same tiny function. A patch deliverable is reviewable code, not
evidence it was applied, merged, tagged, or published.

For a fixed candidate, replace assertions that intentionally characterize
wrong behavior with corrected-behavior assertions. Do not keep tests that
require the bug forever. Do not change the desired expected-contract values
or remove failure cases to achieve a green gate. After fixes, strict mode,
not original characterization mode, is the release criterion.

No package installation, network, fixture command execution, live project
access, or host-modifying test is needed. Use in-memory dictionaries for
validation cases and preserve source fixture bytes.
