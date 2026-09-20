**Not here for terminal commands? [Open the Hive Hub site and try a Hive](https://kody-w.github.io/hive-hub/).**

# Quickstart: your first local join

Say **GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ**. That's the locator for the
public onboarding laboratory. This walkthrough finds it, verifies its full
record, and saves a reversible subscription on your device. It does not run
an agent, clone a repository, or grant membership.

## Before you start: the cold-start release is not live yet

Checked 2026-09-19: the PyPI 0.1.1 wheel lacks `dial --from`, and the live
Pages publisher lacks `dial-snapshot.json`. Do not expect an ordinary
public-index install to complete this new path yet. The sequence below was
verified from a **built cold-start wheel**, against a **served public build**,
in a fresh virtual environment with no source checkout.

The [complete recorded session](PRODUCT_SURFACE_REPORT.md#fresh-wheel-only-quickstart-session)
shows every command and its actual output. Your paths, timestamps, and
time-dependent plan IDs will differ.

For this preview, get the wheel and matching publisher from your maintainer.
Set `WHEELHOUSE` to the absolute directory containing that wheel, and `HUB` to
the publisher's base URL, not its `/hub/` page. The verification publisher was
`http://127.0.0.1:18763/`, serving the generated public files. That loopback
address works only while you have that server running locally; it is not a
public service. The intended deployed base is
`https://kody-w.github.io/hive-hub/` once the matching snapshot is published.

Use Python 3.10+ and a POSIX shell, in a new empty directory outside any
checkout. The directory must have a physical, non-symlink path. On macOS, use
`/private/tmp` rather than the `/tmp` symlink. No RAPP installation, example
files, account setup, or credentials are needed for this public laboratory.

With those prerequisites ready, the commands take about a minute locally;
take the time you need to review the two plans. Publication and deployment
remain release prerequisites, not steps a newcomer should have to repair.

## 1. Install

The two pip settings deliberately select your built wheel, not the older
public-index release:

```bash
: "${WHEELHOUSE:?Set WHEELHOUSE to the directory containing the built cold-start wheel}"
: "${HUB:?Set HUB to the base URL of the matching public build}"
export PIP_NO_INDEX=1
export PIP_FIND_LINKS="$WHEELHOUSE"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install hive-hub
hive-hub --version
```

The setup and activation commands are silent. Pip's paths vary; its success
line and the complete version output are:

```text
Successfully installed hive-hub-0.1.1
{"kind":"hive-hub-version","schema_version":1,"version":"0.1.1"}
```

The old and built wheels currently report the same version. A version string
alone does **not** prove cold-start support; the next command must work.

## 2. Find the laboratory, without fetching yet

```bash
export HIVE_HUB_HOME="$(pwd -P)/.hive-hub"
CHANT="GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ"
RECORD="urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1"
hive-hub dial "$CHANT" --from "$HUB" > dial-plan.json
python -m json.tool dial-plan.json
```

You see the **complete fetch plan**, not a connection result. Its `home` and
`plan_id` depend on your directory and publisher, so never copy a plan ID from
someone else's output. Review these fields:

| Field | Expected value |
| --- | --- |
| `kind` | `public-dial-fetch-plan` |
| `query` | `gorse-quay-dusk-quill-thicket-delta-quartz` |
| `fetches[0].url` | Your `HUB` followed by `api/hive-hub/v1/dial-snapshot.json` |
| `fetches[0].max_bytes` | `2097152` (2 MiB) |
| `fetches[0].expected_sha256` | `null`: this discovery snapshot is mutable |
| `expected_record_id` | `null`: a chant discovers candidates, not a pinned identity |
| `timeout_seconds` / `redirects` | `15` / `forbidden` |
| `registration.scope` / `registration.contracts` | `public` / `inert-only` |
| `registration.overwrite` / `adapter_execution` | `false` / `false` |

There has been no network request or Hive Hub state write. The shell has
saved only `dial-plan.json`. Chants can collide; the full record ID below is
what identifies the laboratory we intend to join.

## 3. Approve the fetch and check the result

If the full plan names the publisher and destination you intend:

```bash
PLAN_ID="$(python -c 'import json; print(json.load(open("dial-plan.json"))["plan_id"])')"
hive-hub dial "$CHANT" --from "$HUB" --apply "$PLAN_ID" > dial-result.json
python - <<'PY'
import json
import os
from pathlib import Path

result = json.loads(Path("dial-result.json").read_text())
expected = "urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1"
assert result["status"] == "resolved", result
assert result["record"]["id"] == expected, "Not the laboratory's full record ID"
print("Resolved:", result["record"]["name"])
print("Record:", result["record"]["id"])
assert not (Path(os.environ["HIVE_HUB_HOME"]) / "state/subscriptions").exists()
print("Not joined yet: no subscription saved.")
PY
```

Exact check output:

```text
Resolved: Hive Hub public onboarding laboratory
Record: urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1
Not joined yet: no subscription saved.
```

The approved request verifies the envelopes, identities, chants, and matching
inert contracts, then imports only matching public candidates. It does not
follow downloaded links or execute anything. Stop on any error or unexpected
identity; do not carry on to the join.

## 4. Review your join

`quickstart` is a local label for you, not a login. Despite its historical
command name, a `join-card` can name a human or an AI.

```bash
hive-hub join-card --principal-kind human --principal-id quickstart \
  --locator "$RECORD" --expected-record-id "$RECORD" > join-card.json
hive-hub bootstrap join-card.json --scope public > join-plan.json
python -m json.tool join-plan.json
```

The first two commands save local review files without printing anything.
The third prints the **complete proposed subscription**. Expect
`"status": "planned"`, `"blocker": null`, and the laboratory's full
`record_id`. Inside `plan`, expect `"action": "create-local-subscription"`,
`"undo_action": "remove-local-subscription"`, and `"adapter_plan": null`.
The principal is `{"id": "quickstart", "kind": "human"}`; the subscription's
`adapter_effects_status` is `"not-required"`. Card/plan/subscription IDs and
the creation time are specific to this run. No subscription has been saved.

## 5. Apply that join and confirm it persisted

If the plan is the local subscription you want, keep the same card and home:

```bash
hive-hub bootstrap join-card.json --scope public --apply > joined.json
hive-hub status > status.json
python - <<'PY'
import json
from pathlib import Path

preview = json.loads(Path("join-plan.json").read_text())
joined = json.loads(Path("joined.json").read_text())
status = json.loads(Path("status.json").read_text())
assert joined["status"] == "applied", joined
assert joined["plan"] == preview["plan"], "The applied join changed from the reviewed plan"
assert joined["plan"]["adapter_plan"] is None
assert status["counts"]["public_records"] == 1, status
assert status["counts"]["local_subscriptions"] == 1, status
assert status["counts"]["local_adapter_plans"] == 0, status
assert status["network_used"] is False, status
print("Joined: Hive Hub public onboarding laboratory")
print("Saved local subscriptions: 1")
print("Adapter effects: not required; no downloaded code executed")
print("Status check: offline")
PY
```

Exact check output:

```text
Joined: Hive Hub public onboarding laboratory
Saved local subscriptions: 1
Adapter effects: not required; no downloaded code executed
Status check: offline
```

**You're joined locally.** The laboratory references a real public repository
at its minimal founding revision. You have a subscription, not a running
autonomous service or new source permissions. Keep `join-plan.json` if you
want to [reverse the subscription](CLI.md#undo-a-quickstart-join).

## If your output differs

| What you see | What to try |
| --- | --- |
| `unrecognized arguments: --from ...` | Use the built cold-start wheel. The currently published wheel is older despite the same version number. |
| A public snapshot fetch error | Check the exact base URL and whether its publisher serves `dial-snapshot.json`. The current live Pages publisher does not. Do not bypass TLS or redirect refusal. |
| Approval does not match | Re-plan after changing the home, query, or publisher; review and approve the new digest. |
| `unreachable` | Check the locator and chosen source. For a private Hive, use an already-authorized source/adapter; this result intentionally does not reveal whether the target exists. |
| An ambiguous result or expectation mismatch | Inspect the candidates and their full IDs; never choose the first merely because its chant matches. |
| A filesystem error | Use a new writable directory with a physical, non-symlink path. Do not weaken no-follow checks. |

For publisher setup, see the
[cold-start publishing notes](REFERENCE.md#cold-start-without-a-checkout).
For commands beyond a first join, see the [CLI reference](CLI.md).
