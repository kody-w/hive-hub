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
