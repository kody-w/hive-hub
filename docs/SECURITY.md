# Security model

Hive Hub core is local-first. It contains no credential broker, repository
client, or code executor. Public discovery has one explicit, lazily loaded
stdlib HTTP client; ordinary dialing and planning remain offline.

## Authority boundaries

- A locator is never proof of identity or authorization.
- Protocol identity is the SHA-256 fingerprint of the exact declaration.
- Learning bundles and adapters must match that fingerprint and conformance
  address.
- Existing adapter/source ACLs are always evaluated outside the core.
- The core never adds a collaborator or stores source credentials.
- Protocol and adapter content stays inert until another system separately
  verifies and approves an effect.

## Public/private noninterference

Public, private, and local records are different directory trees and different
typed records. The standalone public builder is rooted directly at
`books/public`; it has no relative operation capable of escaping to
`books/private`. Public indexes contain neither private records nor policies.

Private lookup checks external ACL authorization before opening the private
book. Missing targets, unauthorized targets, missing policies, malformed or
wrong QR factors, and unapproved access all return the same closed
`unreachable` object.

## Optional QR factor

`acl+qr` is additive; it never replaces ACL. Factors are 32 random bytes in
canonical unpadded base64url. The stored value is:

```text
SHA256(
  "hive-hub/private-access/acl+qr/v1\0" ||
  length(record-id) || record-id ||
  length(scope) || scope ||
  length(epoch) || epoch ||
  raw-factor
)
```

Lengths are unsigned four-byte big-endian values. Verification recomputes the
commitment and uses constant-time digest comparison. Rotating scope or epoch
invalidates the old factor. The factor is transient and absent from every
persisted core contract.

## Filesystem and parser controls

- absolute storage root opened component-by-component with no-follow flags;
- safe relative internal paths with bounded depth;
- regular files only and no symlink traversal;
- bounded bytes, JSON depth, object members, arrays, and collection counts;
- duplicate JSON key and floating-point refusal;
- canonical UTF-8 bytes and sorted keys;
- atomic no-replace writes and byte-address verification before reversal;
- cross-platform per-record interprocess locking around private record and
  policy registration, including rollback;
- no downloaded-code imports, `eval`, `exec`, shell commands, or subprocesses.

The core does not claim resistance to a hostile process with equal operating
system privileges. Hosts should apply normal directory ownership and
permissions.

## Approved public discovery

`dial --from` first returns a content-addressed plan without requests or writes.
Its exact digest is required to perform the single bounded snapshot GET and
inert public registration. Base URL, query, destination, limits, and effect
policy all participate in the digest. It never reads private/local dialbooks,
uses proxy credentials, follows redirects, or follows pointers in the response.
TLS verification remains enabled; plaintext HTTP is limited to explicit
loopback development hosts.

The initial snapshot is mutable discovery data: its byte digest is unknown
before the approved request. Envelope byte hashes, unchanged core identity
bodies, derived chants, artifact hashes, and exact contract relationships are
verified before any registration. A full-ID query pins a record digest; a
chant alone provides only candidate discovery, not publisher authenticity or
authorization. Registration grants no execution permission.

The response and each envelope retain the core's byte/collection/depth limits.
Compressed responses, duplicate keys, floats, and unexpected contract fields
are rejected. Writes are content-addressed, no-replace, and serialized for
public imports; a failed import rolls back only its newly created files.
Existing local content is never overwritten.

## Universal skill network and execution boundary

The skill may use locally installed Git to read an approved repository, but
repository files are data only. A copied contract, lock, setup file, verifier,
or adapter can never select repository code for execution. Joining writes one
local subscription and returns an inert typed adapter plan.

Pinned static declarations are fetched only from origins fixed by the locally
shipped runner. The exact canonical URL, SHA-256, byte count, locator, and
output-root identity are part of the approved plan digest. Before a GET, every
DNS answer must be globally routable; loopback, private, link-local, reserved,
multicast, unspecified, metadata, and redirect targets are refused.

The release privacy scanner stores only irreversible SHA-256 deny digests.
Private CI can add digests through
`HIVE_HUB_PRIVATE_IDENTIFIER_DENY_SHA256`; plaintext private identifiers or
reconstructable string halves are not shipped.
