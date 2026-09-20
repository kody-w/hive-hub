# CLI and local storage

Set `HIVE_HUB_HOME` or pass `--home`. The core creates only the bounded
directories used by the selected operation.

```text
<home>/
  registry/
    declarations/
    bundles/
    adapters/
    receipts/
  books/
    local/records/
    public/records/
    public/indexes/
    private/records/
    private/policies/
    private/indexes/
    private/transactions/
  state/
    plans/
    adapter-plans/
    subscriptions/
```

Files are content-addressed or identity-addressed JSON. Creation writes and
fsyncs a same-directory file, atomically links it into an absent destination,
and refuses different bytes at an existing path. Components and input files
are opened with no-follow semantics and must be regular files.

## Lifecycle

1. `learn DECLARATION BUNDLE` validates matching protocol and conformance
   addresses and stores both as inert data.
2. `adapter register REGISTRATION` validates the same declaration and emits a
   closed receipt.
3. `register SCOPE RECORD` validates all exact references. Private registration
   also writes a one-to-one private policy.
4. `chant derive DIAL_ID` derives `hive-hub-chant/1`; `chant parse CHANT`
   accepts case/spaces and emits canonical lowercase hyphens; `chant verify`
   checks the binding to the full ID.
5. `dial QUERY` resolves either full-id spelling, an exact URL, a derived chant,
   or an existing legacy core chant label. It never fetches implicitly.
6. `join-card` creates a human/AI bootstrap intent.
7. `subscribe plan CARD` performs no mutation.
8. `subscribe apply PLAN` saves only local state and inert adapter effects.
9. `subscribe revert PLAN` removes only the exact subscription bytes described
   by that plan.

`bootstrap CARD` combines dial and planning for one card. Add `--apply` to save
the local subscription. It never performs an adapter effect.

```bash
hive-hub chant derive \
  dial:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1
hive-hub chant parse "GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ"
hive-hub chant verify \
  dial:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1 \
  gorse-quay-dusk-quill-thicket-delta-quartz
```

A chant is only a collisionable candidate locator. Dialing still verifies the
complete Dial Record ID. Display/search aliases such as repository slugs are
not parsed as chants.

## Explicit public discovery

```bash
hive-hub dial "GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ" \
  --from https://kody-w.github.io/hive-hub/
# Inspect the plan, then repeat with --apply and its exact plan_id.
```

The plan is computed offline without opening or creating the home directory.
It binds the normalized query, exact destination home, one snapshot URL,
2 MiB response cap, 15-second network timeout, redirect refusal, public-only
registration, and no-overwrite/rollback behavior. A changed query, base URL,
home, or policy invalidates approval. `expected_sha256: null` describes the
mutable snapshot honestly; a full ID supplies `expected_record_id` separately.

Apply performs exactly that GET with stdlib `urllib`, no ambient proxy
credentials, no redirects, and no following of downloaded links. Each web
record is capped at 128 KiB, including its final LF, and the snapshot at 256
records. Duplicate keys, floats, excessive depth, bad byte hashes, mismatched
core identity/chant/contracts, and private records fail before registration.
Matching records and their inert contracts use atomic no-replace writes;
failure removes only files newly created by that import. Re-applying is
idempotent. URL-only records advertise a derived chant in local indexes without
modifying their hashed `chants` array. Existing legacy label arrays remain
unchanged; their intrinsic ID-derived chant also resolves without consuming
an additional slot in a full legacy index.
Remote `--from` chant selection always verifies the ID-derived chant, including
when matching records already in the public book. A stored legacy label cannot
impersonate another record's canonical published chant.

`--from` accepts only `auto` or `public` scope and refuses ACL/QR options.
Absent and unauthorized HTTP responses share one sanitized failure.
Use the user's existing source ACL through a separate adapter for private
targets; this public import does not add collaborators or broker access.
HTTPS is required, except for explicit `127.0.0.1`, `::1`, or `localhost`
development servers. For a newly built site use `http://127.0.0.1:8123/`.
An old publisher without `dial-snapshot.json` fails explicitly, without a
fallback fetch or claimed resolution.

Keep the home on a physical, non-symlink path. On macOS, `/tmp` itself is a
symlink; use `/private/tmp` for a temporary home rather than weakening the
storage no-follow policy.

## Optional built-in adapter contracts

The integrated adapter package is loaded only when a built-in adapter command
is selected:

```bash
hive-hub adapter builtin list
hive-hub adapter builtin show github-repository
hive-hub adapter builtin install github-repository
hive-hub adapter builtin install github-repository --apply PLAN_ID
```

The first install invocation returns a content-addressed local-write plan.
Applying its exact id stores only the protocol declaration, inert learning
bundle, adapter registration, and receipt. It does not probe a source or
execute an adapter. If the optional adapter package is absent, the core and all
other commands continue to work.

## Private input

The core does not authenticate against a source. An adapter must first evaluate
the existing source ACL and pass only the resulting authorization boolean.

For `acl+qr`, pipe the factor separately:

```bash
printf '%s\n' "$HIVE_QR_FACTOR" |
  hive-hub --home state dial PRIVATE_ID \
    --scope private --acl-authorized --qr-fragment-stdin
```

Do not put the factor in command arguments, JSON, URLs, cards, files, logs, or
browser storage. Error JSON never echoes it.

## Exit behavior

- `0`: successful command, including an `unreachable` result.
- `2`: contract, argument, content-integrity, or approved-fetch failure.
- `3`: sanitized filesystem failure.

Output is one canonical JSON object on stdout. Errors are one canonical JSON
object on stderr.
