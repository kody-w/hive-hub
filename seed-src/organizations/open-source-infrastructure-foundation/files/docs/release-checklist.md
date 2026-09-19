# Release acceptance checklist

**Planning material only. No release, tag, signature, or upload exists.**

1. Desired behavior remains identical to `docs/contract.md`.
2. Both patches are reviewed in order and applied only to an explicitly
   selected candidate copy owned by the consumer.
3. Strict `check_acceptance.py` exits 0 with all three cases passing.
4. Candidate regression tests check unique counts, chronological reduction,
   same-minute tie-breaking, conflict rejection, invalid inputs, and no
   in-memory mutation.
5. Original bug-characterization assertions are updated to fixed behavior;
   desired acceptance fixtures are not weakened.
6. Input limits and no-network/no-write boundaries remain intact.
7. Candidate public-source file hashes, test commands, environment, original
   permission notice, and unresolved limitations are recorded.
8. Maintainer recommendation is explicit, but publication and signing still
   require separate real owner authority.
9. A proposed destination, version, artifact inventory, and withdrawal plan
   are reviewed before any external operation.

Do not use a zero exit from `--characterize` as item 3. It means the known
failures were reproduced, and the result explicitly says release-ineligible.

Remaining limitations even after repairs: no durable event store, streaming,
authentication, real-time coordination, causal clocks, concurrency, audit
signatures, or proof that a work item was actually opened or closed. This is
an offline reducer of synthetic data, not production infrastructure.
