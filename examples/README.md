# Examples

## Generic non-RAPP example

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

## Folder Hive (`hive-md`, experimental)

The `hive-md/` documents declare the experimental `hive-md` protocol for folder
Hives, as defined by
[`HIVE-MD.md`](https://github.com/kody-w/rapp-model-hive/blob/2bd7c95152ede719b6418b80e2bdc2cd457bf711/HIVE-MD.md)
in `kody-w/rapp-model-hive` at commit `2bd7c95`, and a public dial record for
that repository's synthetic Contoso model Hive. Avery founded it with a public
test key derived from a published label; its root commit and founder
fingerprint come from the repository's example history.

The example Hive is a published snapshot with **no live shared copy**. Its
`address` uses the reserved `.invalid` domain and resolves nowhere, so the
Brainstem step below cannot reach it. `public_copy` points at the reviewed
public copy folder in that repository.

| Pin | Value |
| --- | --- |
| `address` | `https://contoso.invalid/hives/contoso-onboarding.git` (resolves nowhere) |
| `hive` | `185d0eb5d4b1247b260042d0d840d5c3` |
| `root` | `f934db89e0c73d71843d634b8ddbd53154732735` |
| `founder` | `SHA256:q18VTrWDieC+Sc25wpbcIHm4/gUotkmUJpyFgDeOdyY` |
| `public_copy` | [`example/contoso-onboarding-public`](https://github.com/kody-w/rapp-model-hive/tree/2bd7c95152ede719b6418b80e2bdc2cd457bf711/example/contoso-onboarding-public) at `2bd7c95` |

The pins travel as the inert learning artifact `hive-md/dial-pins.json`, so the
Dial Record ID binds them through its learning bundle; the record's URLs are
its URL-valued pins. The conformance contract names `HIVE-MD.md` and the
checker `agents/hive_agent.py check` by SHA-256 at that commit. The inert
adapter registration points at the opt-in `adapters.hive_md` adapter, which
only validates the pins and hands them to your Brainstem.

Regenerate the documents (a test checks that they are byte-for-byte current):

```bash
PYTHONPATH=src:. python examples/build_hive_md.py
```

Walk through the join:

```bash
export HIVE_HUB_HOME="$PWD/.hive-hub"
hive-hub learn examples/hive-md/protocol-declaration.json examples/hive-md/learning-bundle.json
hive-hub adapter register examples/hive-md/adapter-registration.json
hive-hub register public examples/hive-md/public-dial-record.json
hive-hub dial "TOR TOR CRAG LEDGE VINE ISLET NORTH" --scope public
hive-hub bootstrap examples/hive-md/human-join-card.json --scope public
```

Both join cards carry one inert adapter-plan effect, `brainstem-hive-join`. The
next step happens in your own Brainstem: the Hive agent `join` with exactly
`address` and `id` = `root`. It proposes first and, after your yes in a later
turn, checks every commit from the root and files one SSH-signed request file
(`request: rapp-hive`); members admit it by moving it into
`members/<name>/keys/`. Hive Hub saves only a reversible local subscription,
never writes into the Hive, never runs the Hive agent, and never reaches the
address, so a private shared copy looks the same as a missing one.
