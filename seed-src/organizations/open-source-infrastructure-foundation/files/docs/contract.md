# Line Ledger desired behavior

All supplied event records are **SYNTHETIC**. This is a local reference data
contract, not a messaging protocol or authority-bearing event format.

## Input

A UTF-8 JSONL file of at most 1 MiB and at most 5,000 nonblank records. Each
line is at most 16 KiB. Every event has exactly:

- `classification`: the literal `SYNTHETIC` for this public reference.
- `event_id`: lowercase-hyphenated text, 1–40 characters.
- `item_id`: lowercase-hyphenated text, 1–40 characters.
- `action`: `open` or `close`.
- `at_minute`: integer 0–1,000,000; booleans are not integers here.

Empty files summarize to zero events/items. Blank lines are ignored. Invalid
JSON, duplicate JSON object keys, unknown fields/actions, invalid values, and
conflicting reuse of one event ID are rejected. A close without an earlier
open is permitted and leaves that item closed; this is state reduction, not
process authorization.

## Desired reduction

1. Validate the complete bounded input.
2. Deduplicate identical event IDs. An ID with any different payload is an
   error, not a last-write-wins update.
3. Sort unique events by `(at_minute, event_id)`, ascending. At equal minute,
   lexically later event ID is applied last. This tie rule is deterministic,
   not a claim of causal truth.
4. Apply open/close actions, counting unique events per item.
5. Return items sorted by item ID, each with final state, unique event count,
   and last applied minute; return global event/open/closed counts.

Do not mutate input dictionaries or add I/O to reduction. No timestamps are
inferred from the machine clock. No commands are interpreted from strings.

## Deliberate gaps in version 0.0.0-reference

The supplied reducer validates conflicts but does not remove identical
duplicates, and it reduces arrival order without step 3. The original
reference therefore fails two desired-behavior fixtures. A future repair must
change implementation and regression evidence, not the desired contract.
