# Product surface execution report

Verified on 2026-09-19 (America/New_York), against the cold-start source at
`3249f33` plus the scoped changes below. This is a historical acceptance
record, not a claim that the preview wheel or site has been released.

## Delivered

| Commit | Change |
| --- | --- |
| `4b6eb2d` | Product-first README, first-line site links, tested quickstart and undo instructions, complete technical reference moved to `docs/REFERENCE.md`. |
| `e0bfe14` | Laboratory chant and real dial-plan command in the hero, seeds second, clearer join-page guidance, regenerated HTML/CSS and their public hash entries. |

The README is now 154 lines with a 99-word introduction before the quickstart.
The former technical content remains in the implementation reference; security
boundaries were not removed to shorten the front door.

Only the owned README, documentation, renderer, and build-generated `hub/` and
`api/` output changed. No `src/`, `tests/`, adapter, skill, example, CI, package,
or public-input files changed. Item 4's error-message implementation and new
repository test were deliberately left to their owner. No push, tag, or PR
was made.

## Verification method

Build/test scratch work and missing dependencies were isolated in a local
verification clone, rather than creating dependency or test scratch directories
in the shared checkout. The exact required commands ran there. All 638
pre-existing tracked files and the two new guides were byte-compared against
the working checkout after the generated output was copied back.

`npm run build` regenerated the public output. The only changed public bytes
are `hub/index.html`, `hub/join/index.html`, `hub/assets/hub.css`, and the three
corresponding entries in `api/hive-hub/v1/hashes.json`. The file set, public
input audit, immutable records, IDs, chants, contracts, cards, QR images, seed
ZIPs, receipts, and runtime JavaScript remain byte-identical.

All five Bash blocks in [QUICKSTART.md](QUICKSTART.md) were extracted and run
unchanged, in order, in a fresh venv outside any checkout. Pip installed the
built wheel with public indexes disabled. A second process verified that the
subscription persisted and that the import came from that venv, not the source
tree. All three README quickstart blocks also ran unchanged in a separate
fresh venv. The documented undo removed the subscription, and reapplying the
same reviewed plan restored it.

### Content truth audit

Checked seven reader-facing Markdown documents, their internal file links,
17 unique external URLs, numeric/contract claims, and cross-repository
references. All 17 external URLs returned complete non-404 content: HTML
titles, JSON kinds, or the actual skill/instructions text were inspected,
not just status codes. Internal Markdown file targets exist.

The live seed catalog and the generated build both contain ten organizations.
The required gate verified 341 seed-package files, 249 public files, 79
immutable objects, 22 QR images, 77 explicit public inputs, and two receipts.
The seven-word/128-word/49-bit derivation and the QR-factor and fetch bounds
are covered by the existing conformance tests and the captured fetch plan.
GitHub's API confirmed the laboratory's exact founding commit
`8e9ee55a7eb9fe4b4aaa084290e1916c0edcade9` and the RAPPID vocabulary-provenance
commit `c988d7975dadb6a8f055183cdbc4cbb17adfe2ae`.

No fabricated reference or confirmed-dead reader link was found. The missing
cold-start snapshot is real deployment lag, explicitly documented below, not
evidence that the laboratory or its repository does not exist.

## Required acceptance output

### `npm run verify`

Verbatim output; exit code 0.

<!-- evidence:npm-verify.txt -->
```text
> hive-hub-static-web@0.1.1 verify
> npm run check:release && npm run build && npm run check && npm test && npm run check:generated && npm run check:receipts


> hive-hub-static-web@0.1.1 check:release
> python3 -B scripts/sync_integrated_release.py --check && python3 -B scripts/update_agent_lock.py --check && python3 -B scripts/check_organization_seeds.py

integrated release contracts are current
agent.lock is current
{"authority": false, "kind": "organization-seed-conformance", "nativeFixtures": [], "packageFiles": 341, "scope": "isolated temporary test fixtures; no user workspace or estate activated", "seeds": 10}

> hive-hub-static-web@0.1.1 build
> node scripts/build.mjs --manifest public-manifest.json --out .

Built 249 public files from 77 explicit inputs (explicit-public-only-v1).

> hive-hub-static-web@0.1.1 check
> node scripts/check.mjs --root . --manifest public-manifest.json

Checked 249 public files, 79 immutable objects, 22 QR SVG, and 77 explicit inputs.

> hive-hub-static-web@0.1.1 test
> node --test tests/*.test.mjs

✔ withdrawal approval binds the exact prior manifest and rejects malformed policy (0.514125ms)
✔ withdrawal requires explicit approval and removal of prior receipt bytes (2989.011791ms)
✔ build is byte-for-byte deterministic (2363.796916ms)
✔ committed public records share the core identity body and derived chant (15.293459ms)
✔ generated surface passes links, hashes, security, and accessibility gates (279.287375ms)
✔ example record is exact and grants no authority or semantic compatibility (0.41825ms)
✔ hive-hub-chant/1 is exact, human-friendly, and protocol-neutral (0.217ms)
✔ public laboratory preserves its original receipt and appends the identity migration (0.472875ms)
✔ public build input reader never scans adjacent private books (4.220875ms)
✔ public QR envelope is locator-only and sensitive cards stay local (332.467416ms)
✔ bare join URL guides the visitor without fetching or reporting verification failure (1.267666ms)
✔ generated join script executes the real core camera-card path (2.450125ms)
✔ organization join verifies the exact package and refuses a different seed (5.377417ms)
ℹ tests 13
ℹ suites 0
ℹ pass 13
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 5064.947167

> hive-hub-static-web@0.1.1 check:generated
> node scripts/compare-build.mjs --manifest public-manifest.json --root .

Fresh deterministic build matches 249 public files.

> hive-hub-static-web@0.1.1 check:receipts
> node scripts/check-receipts.mjs --manifest public-manifest.json

Validated 2 append-only receipt(s).
```

### `PYTHONPATH=src:. python3 -B -m unittest discover -s tests -t .`

Verbatim output; exit code 0.

<!-- evidence:python-unittest.txt -->
```text
..............................................................................................................
----------------------------------------------------------------------
Ran 110 tests in 12.272s

OK
```

### Fresh wheel-only quickstart session

This is the complete command/output session, not a simulated example.
`WHEELHOUSE` was supplied as the temporary directory containing the built wheel;
`HUB` was `http://127.0.0.1:18763/`, serving only generated public files.
The wheel's SHA-256 was
`4c10dd22346e920f0cbc1adec2e823a931381f9196ef7f8db8a565077cccd979`.
There was no source checkout or source-tree example in the client directory;
no separate adapter installation was needed.

<!-- evidence:quickstart-session.txt -->
```text
Fresh client directory (no checkout): /private/tmp/hive-hub-quickstart-wvkb16lu
$ : "${WHEELHOUSE:?Set WHEELHOUSE to the directory containing the built cold-start wheel}"
: "${HUB:?Set HUB to the base URL of the matching public build}"
export PIP_NO_INDEX=1
export PIP_FIND_LINKS="$WHEELHOUSE"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install hive-hub
hive-hub --version
Looking in links: /private/tmp/hive-hub-wheelhouse-khlukiyy
Processing /private/tmp/hive-hub-wheelhouse-khlukiyy/hive_hub-0.1.1-py3-none-any.whl
Installing collected packages: hive-hub
Successfully installed hive-hub-0.1.1
{"kind":"hive-hub-version","schema_version":1,"version":"0.1.1"}
$ export HIVE_HUB_HOME="$(pwd -P)/.hive-hub"
CHANT="GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ"
RECORD="urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1"
hive-hub dial "$CHANT" --from "$HUB" > dial-plan.json
python -m json.tool dial-plan.json
{
    "adapter_execution": false,
    "expected_record_id": null,
    "fetches": [
        {
            "expected_sha256": null,
            "max_bytes": 2097152,
            "url": "http://127.0.0.1:18763/api/hive-hub/v1/dial-snapshot.json"
        }
    ],
    "home": "/private/tmp/hive-hub-quickstart-wvkb16lu/.hive-hub",
    "kind": "public-dial-fetch-plan",
    "plan_id": "urn:hivehub:sha256:e34f52304dffe3d8445cae21a782f9b34b4737207abf2538d8b5b15e6244a1db",
    "query": "gorse-quay-dusk-quill-thicket-delta-quartz",
    "redirects": "forbidden",
    "registration": {
        "contracts": "inert-only",
        "max_records": 256,
        "overwrite": false,
        "rollback": "remove-only-created-content-addressed-files",
        "scope": "public",
        "selection": "verified-query-candidates-only"
    },
    "schema_version": 1,
    "timeout_seconds": 15
}
$ PLAN_ID="$(python -c 'import json; print(json.load(open("dial-plan.json"))["plan_id"])')"
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
Resolved: Hive Hub public onboarding laboratory
Record: urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1
Not joined yet: no subscription saved.
$ hive-hub join-card --principal-kind human --principal-id quickstart \
  --locator "$RECORD" --expected-record-id "$RECORD" > join-card.json
hive-hub bootstrap join-card.json --scope public > join-plan.json
python -m json.tool join-plan.json
{
    "blocker": null,
    "candidate_ids": [],
    "card_id": "urn:hivehub:sha256:41ef031593f27e0f7bf74e70b038e5f1102c9ffa20a1afe9cef0e3b912325c2a",
    "kind": "bootstrap-result",
    "plan": {
        "action": "create-local-subscription",
        "adapter_plan": null,
        "card_id": "urn:hivehub:sha256:41ef031593f27e0f7bf74e70b038e5f1102c9ffa20a1afe9cef0e3b912325c2a",
        "kind": "local-subscription-plan",
        "plan_id": "urn:hivehub:sha256:a456dc9e4901fde3cc3d1d8dc2af49e78113073b3d3cdeba5474032f69b2f259",
        "schema_version": 1,
        "subscription": {
            "adapter_effects_status": "not-required",
            "adapter_plan_address": null,
            "adapter_registration_address": "urn:hivehub:sha256:de6978beaa4c9c2243fd28afbd8c95559640b18494a00a2341bafdf378cfff8e",
            "created_at": "2026-09-20T01:02:54Z",
            "id": "urn:hivehub:sha256:89237ea9e9ed254ba506e16909f7ed93d5db5928d2c0800fa746b4e7462b04e3",
            "kind": "local-subscription",
            "learning_bundle_address": "urn:hivehub:sha256:6351b6f97aa2115318b63f50cfbd531015c2ced86fe84a32e8c4f277fb6cb084",
            "locator": "urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1",
            "principal": {
                "id": "quickstart",
                "kind": "human"
            },
            "protocol_fingerprint": "urn:hivehub:sha256:35b487915e890e5872629b23551e5300092e5464eadce799cd0683948c37339a",
            "record_id": "urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1",
            "record_visibility": "public",
            "schema_version": 1,
            "state": "active"
        },
        "undo_action": "remove-local-subscription"
    },
    "record_id": "urn:hivehub:sha256:9302697cb9068ededacf36b8ad9197467dd9437589295f7350833c1358fceaf1",
    "schema_version": 1,
    "status": "planned",
    "subscription_address": null
}
$ hive-hub bootstrap join-card.json --scope public --apply > joined.json
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
Joined: Hive Hub public onboarding laboratory
Saved local subscriptions: 1
Adapter effects: not required; no downloaded code executed
Status check: offline
Quickstart exit code: 0
```

### Four indistinguishable private failures

A temporary verification harness exercised the actual CLI stdout, including
the final newline, against synthetic fixtures. It made no repository test or
source changes. The fourth call removed only the synthetic fixture's policy
before dialing it again.

<!-- evidence:unreachable.txt -->
```text
private absence: {"candidates":[],"kind":"dial-result","query_kind":"undisclosed","record":null,"schema_version":1,"status":"unreachable"}
failed ACL: {"candidates":[],"kind":"dial-result","query_kind":"undisclosed","record":null,"schema_version":1,"status":"unreachable"}
wrong QR factor: {"candidates":[],"kind":"dial-result","query_kind":"undisclosed","record":null,"schema_version":1,"status":"unreachable"}
missing policy: {"candidates":[],"kind":"dial-result","query_kind":"undisclosed","record":null,"schema_version":1,"status":"unreachable"}
PASS: all four CLI stdout results are byte-identical (122 bytes including LF).
```

## Rendered browser review

I read the rendered page in the connected browser, not just the HTML or a
successful render response. The browser's resize operation reported success
without changing its actual viewport. To avoid claiming a false mobile check,
I used a temporary same-origin review frame around the unmodified generated
page and measured the child viewport at exactly 1280 and 390 CSS pixels.
Screenshots were fitted to the available display after layout; this was not
physical-device emulation or a CSS change to the product.

| Viewport | What the hero actually looks like |
| --- | --- |
| 1280px | Light green-white background, dark headline on one line, very large deep-green chant over two lines: `GORSE QUAY DUSK QUILL` / `THICKET DELTA QUARTZ`. The short explanation is followed by a dark single-line command panel and a green laboratory-card button. The organization heading starts the second section. |
| 390px | Brand and navigation stack. The headline wraps to two lines; the chant is three lines: `GORSE QUAY DUSK` / `QUILL THICKET` / `DELTA QUARTZ`. The command wraps into three readable lines without cutting the flag or URL. The green button and explanatory link stack above the install/review disclosure. Seeds follow in a one-column layout. |

Measured chant sizes were 60.16px and 32.3px respectively. Page scroll widths
equaled the viewport widths (1280 and 390), with no horizontal page overflow.
At 390px the command ended at y=680.49 and the join button at y=765.23.
All ten seed cards remained present. The bare join page displayed its help
state, kept the failure alert hidden, and requested resources only from the
local origin. Only the review tabs created for this task were closed.

## Flags / surprises

1. **The requested live cold start is not released.** The actual public PyPI
   wheel has no `--from` argument, and the public Pages snapshot returns HTTP
   404. GitHub's current published API directory also lacks that file. The
   built-wheel quickstart genuinely joins the public laboratory through the
   served build, but this is not proof that a newcomer can do it against the
   deployed publisher today. Publishing the wheel and snapshot is outside this
   copy-only job, and no release was attempted.

2. **Both wheels say 0.1.1.** Version output alone cannot distinguish the old
   published wheel from the cold-start build. The guide makes the wheel source
   explicit instead of treating the version string as capability evidence.

3. **"One command gets you in" conflicts with the approval contract.** The hero
   command only previews a fetch. Calling that "joined" would be false. The
   copy says so and preserves both the fetch approval and the subscription
   review. "Joined" means saved local state, not running agents, access,
   activated organizations, or authority.

4. **Two old README absolutes were too broad.** Not every successful invocation
   is JSON: `--help` is text. Argument-parser errors can also repeat invalid
   arguments; a harmless synthetic argument confirmed this. The reference now
   explains both exceptions and retains the instruction to keep QR factors on
   stdin. Core contracts exclude QR secrets, while the separate local-only
   sensitive-card tool intentionally has an unlock field; that distinction is
   now explicit rather than contradictory.

5. **The unowned release inventory needs its owner's refresh.**
   `python3 -B scripts/build_release_manifest.py --check` returned exit code 1:
   `release/release-manifest.json is out of date`. The surface/doc changes make
   its previous file inventory stale. It was not changed because `release/`
   is outside this job's ownership. The requested npm and Python gates both
   passed; the anticipated smoke-HTTP/remote-dial failures did not occur in
   those runs.

6. **Presentation hashes necessarily change, identities do not.** Regenerating
   changed HTML/CSS updates their entries in the public hash manifest. No
   content-addressed protocol object, Dial Record, chant, card, QR, or wire
   format changed.

The live CLI failure was also exercised with the built wheel, after approving
its exact fetch plan:

<!-- evidence:live-failure.txt -->
```text
$ hive-hub --home /private/tmp/hive-hub-quickstart-wvkb16lu/live-state dial 'GORSE QUAY DUSK QUILL THICKET DELTA QUARTZ' --from https://kody-w.github.io/hive-hub/ --apply urn:hivehub:sha256:b6d4e975f639508dd6b29f2a17490742fc325634a04770385c5f626b1e1e6476
{"error":{"code":"fetch-error","message":"public Hub snapshot is unreachable"},"ok":false}
Exit code: 2
No Hive Hub home was created by the failed live fetch.
```
