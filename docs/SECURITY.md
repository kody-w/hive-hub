# Security model

Hive Hub core is a local data and planning library. It contains no network
client, credential broker, repository client, or code executor.

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
- no dynamic imports, `eval`, `exec`, shell commands, or subprocesses.

The core does not claim resistance to a hostile process with equal operating
system privileges. Hosts should apply normal directory ownership and
permissions.
