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
4. `dial QUERY` resolves a full id, exact URL, or normalized chant.
5. `join-card` creates a human/AI bootstrap intent.
6. `subscribe plan CARD` performs no mutation.
7. `subscribe apply PLAN` saves only local state and inert adapter effects.
8. `subscribe revert PLAN` removes only the exact subscription bytes described
   by that plan.

`bootstrap CARD` combines dial and planning for one card. Add `--apply` to save
the local subscription. It never performs an adapter effect.

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
