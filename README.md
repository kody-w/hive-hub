**Not here for code? [Open the Hive Hub site to find a Hive](https://kody-w.github.io/hive-hub/).**

# Hive Hub

A **Hive** is a place for people and AI to work together, with a declared way
to connect. Hive Hub helps you find one and check its rules before you join.

Instead of spelling out a long address, say seven words:

**GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ**

That's the chant for the public onboarding laboratory. A chant finds
candidates; it isn't a password or proof of identity. Verify the full record,
review the plan, and save a local subscription. Nothing downloaded runs,
and joining grants no new access.

Any AI, any declared Hive protocol. No RAPP runtime required.

## Quickstart

**Release gate:** the public PyPI 0.1.1 wheel does not yet have `dial --from`,
and the live Pages site does not yet serve `dial-snapshot.json` (checked
2026-09-19). A bare public-index install cannot complete this new CLI path
today. The commands below were run with a built cold-start wheel and a served
public build, from a fresh virtual environment with no checkout.

Use the [step-by-step quickstart](docs/QUICKSTART.md) to set up that preview,
including its wheel source and `HUB` URL, and see the exact success checks.
Once that environment is ready:

```bash
python -m pip install hive-hub
export HIVE_HUB_HOME="$(pwd -P)/.hive-hub"
CHANT="GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ"
RECORD="urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1"
hive-hub dial "$CHANT" --from "$HUB" > dial-plan.json
python -m json.tool dial-plan.json
```

That previews one bounded public fetch; it makes no request or Hive Hub state
write. Review the URL, destination, and limits before approving the exact plan:

```bash
PLAN_ID="$(python -c 'import json; print(json.load(open("dial-plan.json"))["plan_id"])')"
hive-hub dial "$CHANT" --from "$HUB" --apply "$PLAN_ID"
hive-hub join-card --principal-kind human --principal-id quickstart \
  --locator "$RECORD" --expected-record-id "$RECORD" > join-card.json
hive-hub bootstrap join-card.json --scope public
```

Check that dialing says `"status":"resolved"` for the laboratory's full record,
then review the `"status":"planned"` subscription. If it is the join you want:

```bash
hive-hub bootstrap join-card.json --scope public --apply
hive-hub status
```

Success is `"status":"applied"`, then `"local_subscriptions":1` in this fresh
home. **Joined means a reversible local subscription**, not a running agent,
repository clone, activated organization, or membership grant. The laboratory
points to Hive Hub's minimal founding revision, not an autonomous service.

No terminal? Open the [site](https://kody-w.github.io/hive-hub/) and its verified
join card, or give your existing AI the
[Hive Hub skill](skills/hive-hub/SKILL.md). The locked skill's camera card uses
its own compatibility identity; use the supplied card rather than substituting
the new CLI chant. A browser can inspect a Hive, but cannot claim to have saved
a subscription on your device.

## What protects the join

- **A locator is not authority.** Chants, QR codes, URLs, and repositories
  identify candidates. Collisions stay visible; the complete Dial Record ID
  must verify. A seven-word chant is a 49-bit locator, not a secret.
- **Exact rules, not guessed compatibility.** Every record binds its protocol,
  learning bundle, conformance contract, and inert adapter by SHA-256.
  Downloaded instructions and code stay inert; execution needs separate
  verification and approval.
- **Approval before discovery effects.** Public `dial --from` writes nothing
  until you approve its exact plan. Planning makes one bounded read-only GET
  and pins the snapshot's byte digest into the plan; applying refetches and
  refuses to proceed if those bytes changed. It refuses redirects and
  registers only verified matching public candidates. Subscription writes are
  reversible; adapter effects are not executed.
- **Your existing access stays in charge.** Private Hives use their source's
  ACLs. Hive Hub adds no collaborators and brokers no credentials. Optional
  `acl+qr` is a second factor after ACL, never a substitute for it.
- **Private Hives stay private.** Separate dialbooks and an explicit public
  allowlist keep private inputs out of public builds. Private absence, failed
  ACL, missing policy, and a wrong QR factor return the same `unreachable`
  result.
- **The bytes matter.** Closed, bounded JSON contracts reject unknown and
  duplicate keys and floats. Storage uses no-follow reads, regular-file
  checks, and atomic no-replace writes. Locked skill files also require exactly
  one hardlink, with real link-count verification on Windows.

The full [guarantees and implementation reference](docs/REFERENCE.md#guarantees)
preserve the addressing, filesystem, transaction, adapter, and build contracts.
The [security model](docs/SECURITY.md) explains their limits.

## Where this fits

In the experimental RAPP/1 organism map, Hive Hub is the discovery and join
part of the Hive Mind: the network across sovereign Hives. It helps you find a
Hive and plan a join; it never decides who is in. **Transport carries;
signatures decide.** The core still needs no RAPP runtime and no GitHub.

```text
6  You            talk to your Brainstem; confirm every exact plan
5  Brainstem      your own AI; its Hive agent joins folder Hives
4  Your device    your copy of each Hive, one key per device per Hive
3  Hive           where members share work   <-- across: the Hive Mind (Hive Hub)
2  Organization   the accountable body, with exactly one Hive
1  Estate         an owner's signed registry
0  RAPP/1         bytes and identity
```

Folder Hives are declared by the experimental
[`hive-md` protocol](examples/README.md#folder-hive-hive-md-experimental): a
dial record pins the shared copy's address, the Hive id, its first commit, and
the founder key fingerprint. Joining is still a reversible local subscription;
the next step happens in your own Brainstem, whose Hive agent writes one signed
request file. Hive Hub never writes into a Hive or runs its agent. `rapp-hive/1`
remains the Private Hive profile in force; `rapp-hive/2` is frozen as a
research record. See the
[ecosystem map](https://github.com/kody-w/rapp-work/blob/experimental/rapp-work-constitution/ECOSYSTEM.md),
the draft
[constitution](https://github.com/kody-w/rapp-work/blob/experimental/rapp-work-constitution/CONSTITUTION.md),
and the
[Hive folder convention](https://github.com/kody-w/rapp-model-hive/tree/experimental/hive-md).

## Start something of your own

After the laboratory, explore the
[ten public organization seeds](https://kody-w.github.io/hive-hub/hub/#organizations).
Each is a real downloadable RAPP Work starter with scoped teams, a synthetic
case, dependency-linked tasks, original artifacts, an exact file inventory,
a deterministic ZIP, and a verified join card.

They are **starter packages, not activated companies**. Initializing one needs
the exact locally trusted RAPP Work SDK, an owner and destination you choose,
and separately approved native plans. Team work stays in distinct same-world
workspaces; the organization holds pointers. This optional example layer does
not make the Hub core depend on RAPP.

See the [seed catalog and initialization guide](docs/ORGANIZATION_SEEDS.md), or
give your AI the [standalone global network skill](skills/hive-network/SKILL.md)
for local work and owner-reviewed contributions.

## Go deeper when you need to

| I want to... | Start here |
| --- | --- |
| Make my first join and recognize success | [Quickstart](docs/QUICKSTART.md) |
| Look up commands, storage, or undo a subscription | [CLI reference](docs/CLI.md) |
| Understand identities, chants, and wire formats | [Contracts](docs/CONTRACTS.md) |
| Understand private access and safe execution | [Security](docs/SECURITY.md) |
| Use Python, adapters, or the locked Agent Skill | [Implementation reference](docs/REFERENCE.md) |
| Publish a static Hub, verify QR cards, or maintain receipts | [Static publishing reference](docs/REFERENCE.md#static-network) |
| Author a non-RAPP Hive | [Generic example](examples/README.md) |
| Describe a folder Hive (experimental) | [`hive-md` example](examples/README.md#folder-hive-hive-md-experimental) |
| Inspect this release | [Release inventory](RELEASE_INVENTORY.md) and [manifest](release/release-manifest.json) |

The 0.1.1 distribution imports as `hive_hub`, includes the separately
importable optional `adapters` package, and installs `hive-hub`. Runtime
dependencies are empty. Python 3.10, 3.11, and 3.14 are release-gated.
Importing the core does not import an adapter, RAPP tool, GitHub client, or
network runtime.

The static API starts at
[`api/hive-hub/v1/`](https://kody-w.github.io/hive-hub/api/hive-hub/v1/index.json);
AI clients also have [`llms.txt`](https://kody-w.github.io/hive-hub/llms.txt).
The [reference](docs/REFERENCE.md#static-api) documents content addressing,
federation, public-only inputs, QR verification, and append-only receipts.

## Working on Hive Hub

```bash
npm ci --ignore-scripts
npm run verify
PYTHONPATH=src:. python3 -B -m unittest discover -s tests -t .
```

Builds require the explicit pinned `public-manifest.json`; do not hand-edit
generated `hub/` or `api/` files. See the
[public build rules](docs/REFERENCE.md#explicit-public-only-build) and
[complete verification commands](docs/REFERENCE.md#verify) before publishing.
