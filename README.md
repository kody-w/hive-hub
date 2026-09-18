# Hive Hub static network

Hive Hub is a deterministic, no-server discovery surface that is equally usable
by humans and AI clients. The generic core does not assume one Hive protocol,
host, runtime, or authority model.

The committed public surface is:

- `/.well-known/hive-hub.json`
- `/llms.txt`
- `/api/hive-hub/v1/`
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
