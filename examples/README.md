# Generic non-RAPP example

The `generic/` documents describe the fictional Firefly Mesh protocol. They
contain no RAPP or GitHub integration and demonstrate that the core is
protocol-neutral.

Regenerate deterministic documents from the typed API:

```bash
PYTHONPATH=src python examples/build_generic.py
```

Then run the lifecycle shown in the repository README. The human and AI cards
target the same public record; the AI card also carries an inert fetch plan.
No example contains a credential or QR factor.
