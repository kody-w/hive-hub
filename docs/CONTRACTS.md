# Canonical contracts

All Hive Hub contracts are UTF-8 JSON objects with `schema_version: 1`.
Serialization sorts object keys, emits no insignificant whitespace, rejects
floats, and uses the shortest normal JSON representation. Arrays whose meaning
is set-like must already be sorted and unique.

`content_address(value)` returns:

```text
urn:hivehub:sha256:<lowercase SHA-256 of canonical bytes>
```

Dial records, join cards, subscriptions, plans, and receipts contain an
identity address computed from a documented body that omits the identity field.
Other documents use the SHA-256 address of their complete canonical document.
Generic core Dial Record version 1 retains its original identity body,
including any legacy local chant labels. The separate `hive-hub-chant/1`
contract derives from the `dial:sha256:` spelling of that same digest. Neither
conversion nor chant derivation rewrites existing core identity bodies.

The authoritative JSON Schemas are packaged under `hive_hub/schema/` and
available through `hive_hub.get_schema(name)`. Every object schema sets
`additionalProperties: false`; runtime validation also enforces semantic
relationships that JSON Schema cannot express conveniently.

## Protocol and learning

### `conformance-contract`

Names a version and a sorted list of requirement ids and descriptions. Its
complete-document address is referenced by both the protocol declaration and
adapter registration.

### `protocol-declaration`

Declares protocol name and version, media type, capabilities, adapter interface
version, and conformance address. Its complete-document address is the protocol
fingerprint.

### `protocol-fingerprint`

Closed envelope containing algorithm `sha256` and the declaration address.

### `learning-bundle`

References exactly one protocol fingerprint and embeds the matching
conformance contract. Artifacts are inert UTF-8 text with media type, safe
relative name, byte address, and bounded inline content. Learning and
inspection never import or execute an artifact.

## Adapter contracts

### `adapter-registration`

An inert descriptor containing its protocol fingerprint, versions, locator,
conformance address, supported operations, and declared effect kinds. A
registration is data; the core never resolves its locator.

### `adapter-registration-receipt`

Records the registration address, protocol fingerprint, visibility scope,
canonical UTC time, and `registered` status. It has no generic extension map
and cannot carry credentials or QR factors.

### `adapter-plan`

Contains sorted explicit effects. Effect kinds are `authenticate`, `clone`,
`execute`, `fetch`, `write`, or `other`; every effect has
`requires_approval: true`. Applying a local subscription persists this plan but
does not perform any effect.

## Dial and join

### `chant-locator`

Implements `hive-hub-chant/1`. The derivation is
`SHA-256(UTF-8 full canonical Dial Record ID)`, selecting the first seven digest
bytes modulo 128 and mapping them through the frozen vocabulary. Human parsing
accepts case differences and either spaces or canonical hyphens; output is
exactly seven lowercase hyphen-separated words.
Known vocabulary chants are recognized before rejecting opaque QR factors:
a valid 43-character hyphenated chant is not mistaken for a QR secret merely
because its length and characters also fit the base64url pattern.

The vocabulary is byte-exact from
`kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae`, with SHA-256
`325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`.
That provenance does not create a RAPP identity or runtime dependency. A chant
is a collisionable 49-bit candidate locator, never authority, and its complete
Dial Record ID must verify.

### `dial-record`

Contains an addressed identity, display text, one visibility
(`local`/`public`/`private`), exact protocol/bundle/adapter addresses, sorted
absolute URLs, and sorted legacy chant labels. URL fragments and embedded URL
credentials are forbidden. The identity body includes `chants`; putting a
chant derived from that identity back into this array would be circular.

### Published record projection

Every active web record carries `coreRecord`, an exact closed `DialRecord`,
and `coreContracts`, containing the matching closed `protocol`,
`learningBundle`, and `adapter` documents. `urn:hivehub:sha256:<digest>` and
the envelope's `dial:sha256:<digest>` are two spellings of **one** identity,
computed by the existing Python `DialRecord._body`. Core identity bytes have
no trailing newline; web envelope byte addresses include the final LF.

The trusted build-only projector uses the Python contract constructors. It
retains the complete published protocol, learning, conformance, adapter, and
locator documents as hash-verified inert learning artifacts. The projected
registration declares inspection only, not an executable adapter or additional
semantic compatibility. The core record's `chants` array is empty and its URLs
bind the published locator; the presentation envelope derives its one
seven-word chant **after** computing the identity.
Import requires core chant labels to be empty or exactly that ID-derived
chant, never another record's chant or arbitrary legacy display text. Core
URLs must exactly equal the locator projection used by the builder. Envelope
aliases and record IDs must have their declared types, fingerprints must match
their descriptors, and descriptor paths/URLs must be safe, matching,
credential-free HTTPS references. These structural checks do not confer
ownership of a valid display label.

`dial-snapshot.json` packages the active envelopes and their separate web byte
hashes into one bounded response. It contains no private book and requires no
following of URLs in downloaded documents.

### Protocol-specific data

`dial-record` has no protocol extension map. A protocol's per-Hive data travels
as an inert artifact in the record's learning bundle, so the Dial Record ID
binds it through `learning_bundle_address`; URL-valued items also appear in
`urls`. The core never interprets that data; only the protocol's adapter does.

The experimental `hive-md` protocol for folder Hives uses one artifact,
`hive-md/dial-pins.json`: canonical JSON plus one line feed, with exactly
`kind: "hive-md-dial-pins"`, `schema_version: 1`, and these pins:

- `address`: the shared copy's credential-free `ssh`, `https`, or `git` URL,
  never a local path. It may be private; nothing distinguishes a private
  address from a nonexistent one.
- `hive`: the Hive id, 32 lowercase hexadecimal characters.
- `root`: the full 40-hex id of the Hive's first commit.
- `founder`: the founder key's `SHA256:` fingerprint (43 base64 characters).
- optional `public_copy`: the `https` URL of the reviewed public copy.

The record's `urls` are exactly `address` and any `public_copy`. See the
[example](../examples/README.md#folder-hive-hive-md-experimental).

The locked Agent Skill's older dialbook is a separate compatibility format,
not the canonical core identity. Published cards name its unchanged locator
as `legacySkillDialId` and its separately referenced card as `legacySkillCard`.
The primary `cameraAiCard.locator`, public `dialId`, and core record's
`dial:sha256:` spelling all agree. Changing a camera-card locator recomputes
both its closed-contract `card_id` and its web byte address before emitting
the card references and QR. Canonical camera cards target the core client;
only the explicit legacy card targets the older locked runner.
Previously published receipt subjects remain byte-exact historical objects,
outside the active dialbook. The conformance oracle checks every active
record against the core; receipt and content-hash checks protect the archived
publication without pretending it originally contained `coreRecord`.
The all-card oracle also validates every emitted canonical camera card through
`AIJoinCard.from_dict` and checks its binding to the corresponding core record.

### `public-dialbook-index` and `private-dialbook-index`

Contain sorted record summaries plus `chant_candidates` and `url_candidates`.
Each candidate maps to an array of one or more record ids, so collisions are
never overwritten. The two index kinds reject mixed visibility.
Every index advertises the sorted, deduplicated union of legacy labels and
the intrinsic ID-derived chant. Hashed record bodies are unchanged. Existing
array limits still apply; a 256-label record needing a 257th derived entry
cannot be represented by that bounded index/result contract and raises a
typed limit error instead of omitting any candidate.

### `ai-join-card`

Despite its historical name, the principal is explicitly `human` or `ai`.
The card carries a dial locator, optional expectations, and an optional inert
adapter plan. It cannot carry a QR factor.

### `local-subscription`

Records the joined Hive, principal, selected locator, exact protocol
dependencies, and whether adapter effects are `not-required` or
`not-executed`.

### `local-subscription-plan`

Wraps one proposed subscription, optional adapter plan, and the explicit
reversal `remove-local-subscription`. Planning performs no write.

### `bootstrap-result`

Returns one of `planned`, `applied`, `blocked`, or `unreachable`. A blocked
result exposes exactly one highest-precedence blocker. Private reachability
failures contain no record, query kind, candidates, or blocker.

## Private policy

### `private-access-policy`

`acl-only` is the default and stores a null commitment. `acl+qr` stores only a
domain-separated SHA-256 commitment bound to record id, scope, and epoch.
Source ACL authorization is required in both modes.
