# The Enterprise Transformation Firm

**SYNTHETIC case:** Lattice Harbor Supply is a fictional office-supply
enterprise. Its account data, operational facts, money, taxes, and policies
were authored for this seed. Nothing here is tax advice or a real engagement.

The six team workspaces have a concrete transformation case: establish a
reviewable quote-readiness boundary before invoices are issued. Start with the
client brief, original CSV inputs, requirements, and pending task graph.

## Run the working reference boundary

From `files/`, using Python 3.10 or newer:

```sh
python3 -I -B reference/test_quote_flow.py
python3 -I -B reference/quote_flow.py data
```

The utility reads only the four named files in the selected data directory and
prints JSON. It uses Python's standard library, exact decimal arithmetic, and
no network, server, installation, storage mutation, or enterprise adapter.
Tests use the supplied files and in-memory variations; no temporary files.

Expected reference distribution: **2 ready-for-human-approval, 4 needs-review,
2 needs-data**. Readiness is not approval. The deliberately invalid q-105 and
q-107 records are data-quality fixtures, not failed tests. All eight expected
outcomes are in `reference/expected-results.json`.

The program is a minimal calculation/workflow prototype, not an ERP replacement:
it has no inventory allocation, tax determination, invoice numbering,
authorization, persistence, or payment. The task graph turns its concrete
outputs into discovery, architecture, acceptance, and adoption work. Reference
examples are not completed tasks, signed decisions, measured savings, or a
deployed pilot. Any real enterprise data or integration needs a separate
owner-authorized scope.
