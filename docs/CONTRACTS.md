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

### `dial-record`

Contains an addressed identity, display text, one visibility
(`local`/`public`/`private`), exact protocol/bundle/adapter addresses, sorted
absolute URLs, and normalized chants. At least one URL or chant is required.
URL fragments and embedded URL credentials are forbidden.

### `public-dialbook-index` and `private-dialbook-index`

Contain sorted record summaries plus `chant_candidates` and `url_candidates`.
Each candidate maps to an array of one or more record ids, so collisions are
never overwritten. The two index kinds reject mixed visibility.

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
