# Hive Hub

Hive Hub 0.1.0 is one protocol-neutral release containing a typed Python core,
optional stdlib adapters, a universal Agent Skill, and a deterministic static
API/Pages surface. The distribution imports as `hive_hub`, includes the
separately importable `adapters` package, and installs the `hive-hub` command.

Importing the core does not import or require an adapter, RAPP tool, GitHub
client, or network runtime. A Hive declares its exact protocol fingerprint,
content-addressed learning bundle, conformance contract, and inert adapter
registration. Chants, URLs, QR codes, repositories, and static APIs are
locators—not authority.

## Guarantees

- Canonical UTF-8 JSON and `urn:hivehub:sha256:<64hex>` content addresses.
- Closed contracts: unknown keys, duplicate JSON keys, floats, and oversized
  inputs are rejected.
- Physically separate local, public, and private dialbooks.
- The public index builder opens only `<home>/books/public`; it cannot read or
  hash the private book.
- Collision-preserving chant and URL candidate arrays.
- Plan-first local subscriptions. Clone, authentication, fetch, write, and
  execution effects remain explicit inert adapter plans requiring approval.
- Existing source ACLs remain mandatory for private access.
- Private absence, failed ACL, missing policy, and wrong optional QR factor all
  return the identical `unreachable` result.
- No-follow reads, bounded traversal, regular-file checks, atomic no-replace
  writes, and reversible subscription writes.
- No downloaded protocol text, skill, or adapter is executed.
- Built-in adapter contracts are loaded lazily; unavailable RAPP tooling remains
  inert and never becomes a core requirement.

## Install

```bash
python -m pip install hive-hub
hive-hub --help
```

Python 3.10, 3.11, and 3.14 are release-gated. Runtime dependencies are empty.

## CLI

```bash
export HIVE_HUB_HOME="$PWD/.hive-hub"

hive-hub validate examples/generic/protocol-declaration.json
hive-hub learn \
  examples/generic/protocol-declaration.json \
  examples/generic/learning-bundle.json
hive-hub adapter register examples/generic/adapter-registration.json
hive-hub register public examples/generic/public-dial-record.json

hive-hub dial "firefly commons" --scope public
hive-hub inspect "$(python - <<'PY'
import json
print(json.load(open("examples/generic/manifest.json"))["protocol_fingerprint"])
PY
)"
hive-hub subscribe plan examples/generic/ai-join-card.json
hive-hub bootstrap examples/generic/ai-join-card.json --apply
hive-hub status
hive-hub adapter builtin list
hive-hub adapter builtin show github-repository
```

Installing built-in adapter contracts is plan-first. The first command returns
an exact plan id; repeat with `--apply <plan-id>` to store only inert local
contracts and a receipt. It does not execute the adapter.

Every success and failure is one JSON object. Failures use
`{"ok":false,"error":{"code":"...","message":"..."}}` without a traceback or
echoing private input.

Other commands:

```text
hive-hub register local|public|private RECORD
hive-hub dial QUERY [--scope auto|local|public|private]
hive-hub join-card --principal-kind human|ai --principal-id ID --locator QUERY
hive-hub subscribe plan CARD
hive-hub subscribe apply PLAN
hive-hub subscribe revert PLAN
hive-hub index public|private
hive-hub schema list
hive-hub schema show CONTRACT
```

## Python API

```python
from hive_hub import HiveHub, Principal

hub = HiveHub("state")
result = hub.dial("firefly commons", scope="public")
card = hub.create_join_card(
    principal=Principal.create(kind="ai", identifier="agent:example"),
    locator=result.record.id,
)
planned = hub.plan_local_subscription(card)
applied = hub.apply_subscription(planned.plan)
```

`learn_protocol`, `register_adapter`, `register_local_record`,
`register_public_record`, `register_private_record`, `dial`,
`create_join_card`, `plan_local_subscription`, `apply_subscription`,
`revert_subscription`, `inspect_protocol`, and `bootstrap_one` are the main
core APIs. `inspect_bundle` returns the complete inert learning bundle and
artifact text without importing or executing it.

## Private access

`acl-only` is the default. The core accepts an `acl_authorized=True` result only
after an external adapter has applied the source's existing ACL. It never adds
collaborators or brokers credentials.

Optional `acl+qr` adds a second factor after ACL:

- the factor is exactly 256 random bits encoded as unpadded base64url;
- its commitment is domain-separated and bound to record id, scope, and epoch;
- comparison uses `hmac.compare_digest`;
- only the commitment is stored, only in the private policy;
- the fragment is supplied transiently (CLI: `--qr-fragment-stdin`);
- the fragment is forbidden in records, indexes, cards, plans, receipts, and
  locators. Browser integrations must keep it out of persisted browser storage.

Locator-only QR remains the recommended default.

## Documentation

- [Contract and addressing reference](docs/CONTRACTS.md)
- [CLI and storage layout](docs/CLI.md)
- [Security model](docs/SECURITY.md)
- [0.1.0 release inventory](RELEASE_INVENTORY.md)
- [Deterministic release manifest](release/release-manifest.json)
- [Generic non-RAPP example](examples/README.md)

## Neutral adapter package

`adapters/` is a stdlib-only, typed source tree that can be merged into the
core package without importing any RAPP runtime:

| Adapter | Exact protocol |
|---|---|
| GitHub repository locator/probe | `hive-hub-github-repository/1.0` |
| Local filesystem workspace | `hive-hub-local-workspace/1.0` |
| Installed RAPP Work/Hive delegate | `hive-hub-rapp-delegate/1.0` |
| Seven-word RAPPID chant | `rappidex/1-summon-chant` |
| Payphone DoorRef/dial result | `rapp-payphone-dial/1.0` |
| Historical Hub inspector | `legacy-rapp-hub/00ac2f73` |

Each declaration binds its protocol to canonical contract bytes with SHA-256
and includes capability requirements, supported private-access modes, an inert
learning bundle, and local conformance fixtures. The registry performs exact
fingerprint lookup only. An unknown fingerprint returns an inert adapter and
is never routed to RAPP.

The GitHub probe uses `git ls-remote` with caller-owned ambient credentials,
stdin closed, and interactive prompts disabled. Every nonzero response is the
same `unreachable` result, so an absent repository cannot be distinguished
from one the caller cannot access. It never changes repository ACLs or remote
state.

The chant adapter carries the frozen 128-word vocabulary and hash
`325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`.
Chants remain 49-bit locators; collision buckets retain all complete RAPPIDs.
Payphone routing prefixes likewise never authorize: connection requires the
exact full RAPPID.

## Conformance

```sh
python3 -m unittest discover -s adapters/tests -v
ruff check adapters
mypy --strict adapters
```

Fixtures cover canonical GitHub forms, absent/unauthorized indistinguishability,
ambient-token hygiene, no remote writes, exact chant vectors and collision
buckets, new Payphone DoorRef vectors and truncated-ID collisions, and inert
historical malicious instructions.

## Explicit compatibility refusals

- The installed legacy `rapp` Rapid AI Agent Production Pipeline CLI is not a
  RAPP Work/Hive authority delegate. Only `rapp-work` and `rapp-hive` adapter
  entry points are considered.
- The historical RAPPidex “first repository wins” behavior is incompatible
  with collision-safe lookup and is not used.
- Legacy/provisional RAPPID forms are inspection or migration evidence, not
  active chant or Payphone inputs. Active parsing requires the exact lowercase
  RAPP/1 form with a 64-hex tail.
- Historical Payphone Issues/PR mutation rungs and the `no-answer` outcome are
  outside this neutral read-only adapter. Its result is only `connected` or
  `unreachable`.
- `RAPP_Hub@00ac2f73` server, Docker, skill, and instruction surfaces are never
  downloaded, installed, imported, or executed. The adapter reads bounded
  already-local JSON only.

## Static network

Hive Hub is a deterministic, no-server discovery surface that is equally usable
by humans and AI clients. The generic core does not assume one Hive protocol,
host, runtime, or authority model.

The committed public surface is:

- `/.well-known/hive-hub.json`
- `/llms.txt`
- `/api/hive-hub/v1/`
- `/api/hive-hub/v1/core-schemas/`
- `/api/hive-hub/v1/release.json`
- `/hub/`
- `/hub/join/`

Those paths work as ordinary GitHub Pages files and as raw Git repository files.
The Pages workflow publishes only the generated surface, not the build tools or
source documents.

## Safety model

- Chants, URLs, Git references, cards, and QR codes are candidate locators only.
- A chant always maps to an array of candidates and never establishes unique
  authority.
- Every Dial Record binds an exact protocol declaration, learning bundle,
  conformance contract, and adapter by canonical JSON SHA-256.
- Downloaded code, protocol text, skills, and adapters remain inert until
  independently approved and verified.
- Existing source ACLs remain authoritative. The Hub adds no collaborator,
  credential, broker, or private-target oracle.
- The public example claims neither authority nor semantic compatibility.

## Static API

`api/hive-hub/v1/index.json` links the public dialbook, four deterministic
SHA-256 record buckets, federation indexes, content-addressed objects, schemas,
cards, status, hashes, offline seed, and append-only receipt ledger.

Immutable JSON uses canonical UTF-8 bytes with sorted object keys and one final
line feed. Its reference is `sha256:<digest>`, and its path ends in that digest.
Mutable discovery indexes contain hashes for the immutable objects they name.
`hashes.json` covers every generated public file except itself, avoiding a
recursive self-hash.

Federation unions candidate dialbooks and bucket indexes. It does not promote
any peer, chant, or record into authority.

## Explicit public-only build

The build command requires an explicit `public-manifest.json`:

```console
npm ci --ignore-scripts
npm run build
```

The manifest must:

1. declare `classification: "public-only"`;
2. use exactly `sourceRoot: "public-src"`;
3. list every input file individually as `classification: "public"`;
4. pin every input's exact SHA-256; and
5. define complete, non-overlapping record buckets.

The public reader performs no directory discovery. It opens only the manifest
and its allowlisted, pinned files, rejects symlinks and path traversal, and
records the complete read set in `hashes.json`. Tests place an unreadable
private-book sentinel next to an allowed public root and prove it is never
inspected. A traversal entry is rejected before file access.

After intentionally editing a public input, refresh its explicit pin:

```console
npm run pin:public
npm run verify
```

## QR join cards

Public QR SVGs are generated at build time with the exact build-only dependency
in `package-lock.json`. Their fragment contains only:

```json
{"card":"<same-origin content-addressed card URL>","sha256":"<digest>","v":1}
```

`/hub/join/` captures that fragment and immediately removes it with
`history.replaceState` before fetching anything. It then fetches same-origin
static JSON, verifies the card, Dial Record, protocol, learning bundle, adapter,
and conformance contract, and cross-checks `hashes.json`.

Humans receive accessible steps. AI clients can use `?format=json`,
`?format=llms`, `/hub/join/ai.json`, or `/llms.txt`. The browser runtime has no
external scripts, analytics, service workers, persistent storage, telemetry, or
credentialed requests. CSP and no-referrer policies are embedded in each page.

Sensitive locator-plus-unlock cards are a separate local-only tool. It permits
output only under ignored `.hive-hub/private-cards/` or `tests/.work/` paths:

```console
node scripts/generate-sensitive-card.mjs \
  --input .hive-hub/local-card.json \
  --out-dir .hive-hub/private-cards/example
```

Local card input must declare `accessMode: "acl+qr"`. The generated payload
states that the source ACL must succeed first; the QR value is only a second
factor and cannot replace or weaken source authorization.

The public builder never imports or invokes that tool, and public-card
validation rejects sensitive fields.

## Receipts

Receipt source entries are ordered and immutable. Generated receipts are
content-addressed, each receipt links its predecessor, and the ledger head is
published at `api/hive-hub/v1/receipts/index.json`.

Compare a change against an existing branch:

```console
npm run check:receipts -- --base main
```

This rejects removed, reordered, modified, or replaced historical receipt
sources and published receipt objects. Corrections are new receipts rather than
edits.

## Gates

```console
npm run verify
```

The gate rebuilds, validates canonical JSON, links, hashes, content-addressed
paths, bucket coverage, federation candidate arrays, receipt chains, QR SVGs,
runtime restrictions, CSP/referrer metadata, basic accessibility, public-input
isolation, exact example revision, and byte-for-byte reproducibility.

## Universal Agent Skill

`skills/hive-hub/` is a complete Agent Skill for a person or any AI. It accepts
the core `ai-join-card` contract used by the generated camera-AI card as well
as its compact locator-card formats. Copy that folder into a tool's skills
directory and ask it to:

- “dial this hive”
- “join this hive on this device and tell me when you are ready”
- scan a camera/QR Hive card

It accepts a public or private GitHub URL, `owner/repo at branch`, a local path,
a seven-word chant, a full Dial Record ID, or QR/AI join-card JSON. An optional
workspace address can accompany any request.

The locked Python 3.11+ runner uses only the standard library and must run with
isolated mode:

```bash
cd skills/hive-hub
python3 -I -B scripts/run.py decode --locator 'owner/repo at branch'
python3 -I -B scripts/run.py join --locator 'owner/repo at branch'
python3 -I -B scripts/run.py join --locator 'owner/repo at branch' \
  --apply '<exact returned plan digest>'
```

Every network read, local write, or verified adapter execution is planned
first. Existing source access is used without prompting or credential output.
Unknown protocols remain inert and return one blocker with their
content-addressed learning bundle.

## Verify

The core, adapters, skill, generated static surface, release inventory, and
privacy boundary are checked together:

```bash
PYTHONPATH=src:. python3 -B -m unittest \
  tests.test_contracts tests.test_hub tests.test_private_access \
  tests.test_safety_cli tests.test_adapter_runtime -v
python3 -B -m unittest discover -s adapters/tests -t . -v
python3 -B -m unittest tests.test_hive_hub -v
python3 scripts/check.py
python3 scripts/prove.py
npm ci --ignore-scripts
npm run verify
python3 scripts/check_public_release.py
python3 scripts/build_release_manifest.py --check
```

`prove.py` also copies the skill to a path with spaces and verifies that the
copied folder operates without repository context.
