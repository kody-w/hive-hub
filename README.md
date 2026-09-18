# Hive Hub

`hive-hub` 0.1.0 is a typed, standard-library-only Python core for discovering,
learning, dialing, and joining protocol-neutral Hives. The distribution imports
as `hive_hub` and installs the `hive-hub` command.

The core has no RAPP, GitHub, adapter runtime, or network dependency. A Hive
declares its exact protocol fingerprint, content-addressed learning bundle,
conformance contract, and inert adapter registration. Chants, URLs, QR codes,
repositories, and static APIs are locators—not authority.

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
```

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
