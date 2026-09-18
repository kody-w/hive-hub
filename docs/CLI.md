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
5. `dial QUERY` resolves a full id, exact URL, or canonical derived chant.
6. `join-card` creates a human/AI bootstrap intent.
7. `subscribe plan CARD` performs no mutation.
8. `subscribe apply PLAN` saves only local state and inert adapter effects.
9. `subscribe revert PLAN` removes only the exact subscription bytes described
   by that plan.

`bootstrap CARD` combines dial and planning for one card. Add `--apply` to save
the local subscription. It never performs an adapter effect.

```bash
hive-hub chant derive \
  dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32
hive-hub chant parse "JUNIPER QUARTZ HARBOR BIRCH COBALT NOOK FLINT"
hive-hub chant verify \
  dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32 \
  juniper-quartz-harbor-birch-cobalt-nook-flint
```

A chant is only a collisionable candidate locator. Dialing still verifies the
complete Dial Record ID. Display/search aliases such as repository slugs are
not parsed as chants.

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
- `2`: contract or argument validation failure.
- `3`: sanitized filesystem failure.

Output is one canonical JSON object on stdout. Errors are one canonical JSON
object on stderr.
