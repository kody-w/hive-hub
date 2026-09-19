# Replication protocol

**SYNTHETIC computation; protocol is not a completed replication report.**

1. Use the explicitly listed dataset, capacity file, experiment plan, and
   original reference programs. Do not substitute a real library inventory.
2. Record Python version and actual commands. Use a fresh interpreter, no
   installed solver, network, server, or environment-dependent data.
3. Run the authored tests and baseline with `--exact-small`.
4. Check all expected per-scenario algorithm counts. Independently verify
   each item appears once and both capacities hold.
5. Run the experiment twice. Compare the complete JSON results, including
   source hashes and all per-trial arrays. File hashes are public-data
   reproducibility identifiers, not signatures or runtime authority.
6. Compare against the first experiment report. Any mismatch in source bytes
   means a different input, not successful replication of the same run.
7. Report any numerical disagreement, node-limit condition, changed runtime,
   and unperformed check explicitly.

Pass requires exact baseline counts, matching trial arrays and input hashes
for the same interpreter behavior, and all packing invariants. Different
Python random implementations or future version changes may alter seeded
permutations; record the runtime rather than promising indefinite bitwise
identity across every environment. The sorted methods should still be
permutation-invariant because item IDs break ties.

Replication establishes computation on these original synthetic inputs.
Physical fit, operator comprehension, safe handling, business costs, and
demand are separate not-observed domains.
