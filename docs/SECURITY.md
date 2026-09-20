# Security model

Hive Hub core is local-first. It contains no credential broker, repository
client, or code executor. Public discovery has one explicit, lazily loaded
stdlib HTTP client; ordinary local dialing and subscription planning remain
offline. Explicit public-discovery planning performs a read-only snapshot GET.

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
- safe relative internal paths with bounded depth and 255-byte components;
- regular files only and no symlink traversal;
- bounded bytes, JSON depth, object members, arrays, and collection counts;
- duplicate JSON key and floating-point refusal;
- canonical UTF-8 bytes and sorted keys;
- atomic no-replace writes and byte-address verification before reversal;
- cross-platform per-record interprocess locking around private record and
  policy registration, including rollback;
- no downloaded-code imports, `eval`, `exec`, or shell commands; the bounded
  HTTP worker runs only locally installed code.

The core does not claim resistance to a hostile process with equal operating
system privileges. Hosts should apply normal directory ownership and
permissions.

## Approved public discovery

`dial --from` first performs one read-only GET and returns a content-addressed
plan without writes. The snapshot's exact byte SHA-256, base URL, query,
destination, limits, and effect policy all participate in the plan digest.
Apply refetches once and compares the recomputed plan with the approved digest,
refusing changed bytes before registration and requiring a new plan. This
avoids registering content that appeared only after approval.
Neither phase reads private/local dialbooks,
uses proxy credentials, follows redirects, or follows pointers in the response.
TLS verification remains enabled; plaintext HTTP is limited to explicit
loopback development hosts.

The snapshot is mutable discovery data, pinned by the planning read, not an
authenticated statement of publisher authority. Envelope byte hashes, unchanged core identity
bodies, derived chants, artifact hashes, and exact contract relationships are
verified before any registration. A full-ID query pins a record digest; a
chant alone provides only candidate discovery, not publisher authenticity or
authorization. Registration grants no execution permission.

Public imports reject core chant labels other than the exact ID-derived chant
and require the core URL list to match the locator projection. Presentation
record IDs/aliases, fingerprints, and descriptor path/URL/ref values are typed
and validated; valid display labels still do not prove ownership of a name.
Existing locally authored legacy records retain their label semantics. This
is not a retroactive purge or authorization claim about old public-book data.

The response and each envelope retain the core's byte/collection/depth limits.
Every Content-Encoding header is checked, and ambiguous Content-Length headers
are refused. Compressed responses, duplicate keys, floats, and unexpected contract fields
are rejected. Writes are content-addressed, no-replace, and serialized for
public imports; a failed import rolls back only its newly created files.
Existing local content is never overwritten.

One wall-clock deadline covers the whole request, including blocking DNS,
connection/TLS, status line, headers, and body. A disposable spawned worker
isolates only the installed stdlib fetch implementation. On expiry it is
terminated and reaped, rather than leaving a daemon thread fetching after the
CLI has returned. The worker does not write files, register records, or execute
downloaded text. Python API callers use the normal `__main__`-guarded script
pattern required by process spawning.

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
