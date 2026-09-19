# Pocket Queue — federation prime contractor seed

All customer, engagement, partner-submission, and review-fixture data is
**SYNTHETIC**. This is a working local acceptance rehearsal, not a contract,
federation, partner registration, deployment, or completed delivery.

## Specific engagement

Fictional Hearthstep Maker Hall wants a closed, anonymous-ticket rehearsal for
60 synthetic attendees. The prime's own five teams share its own demonstration
world, `demo-federation-prime-contractor`. Proposed partner scopes are split:

| DISCOVERY-ONLY candidate | Proposed public artifact | Dependency |
|---|---|---|
| `applied-invention-lab` | `prototype-spec`: local queue interface/specification | Frozen engagement |
| `enterprise-transformation-firm` | `operating-model`: roles, retention, stop rule | Prototype interface |
| `product-launch-company` | `pilot-kit`: operator steps and truthful closed-pilot disclosure | Prototype + operating model |
| Prime's own integration team | Derived integration report | All three local content checks |

The machine-readable briefs are **unsent and unapproved**. They neither
represent partner consent nor import anyone's workspace. Independent
organizations keep separate worlds. Only separately owner-approved public
artifacts may cross between them. No crossing occurs here.

## Run the actual offline reference

From `files/`, Python 3/stdlib only; no install, server, network, or writes:

```text
python3 -I -B tools/acceptance.py --fixture baseline
python3 -I -B tools/acceptance.py --fixture rework
python3 -I -B tests/test_acceptance.py
```

The baseline intentionally exits **1**, printing a content-rejection report:
the operating-model retention is 1440 minutes instead of at most 120, the
pilot kit references interface version 0 rather than 1, and the prime's derived
integration report is blocked. This is an expected rehearsal result, not a
utility failure.

The corrected local fixture exits **0** and satisfies the same eighteen
criteria. Even then `delivery_authorized` remains false,
`real_partner_submissions` remains false, and `external_effects` stays empty.
Passing a JSON content check is not actual partner acceptance or approval.

The utility enforces declared fields, candidate attribution, fixture-only
visibility, explicit dependency order, finite typed rules, and rejection of
unknown/cyclic/duplicate inputs. It never evaluates source code or retrieves
arbitrary paths. Reports identify fixture JSON pointers and matrix CSV rows.

## What remains real future work

The fixtures are original examples authored in the prime package, not work
received from the candidate organizations. Their offline flags and operator
steps are **declarations**, not dynamic application verification, observed
usability, or proof of a delivered prototype. Owner-approved outreach,
commercial terms, actual public-artifact exchange, application testing, and
real engagement acceptance are absent.

Start with `freeze-prime-engagement`. The task graph connects discovery,
integration, rejection, bounded rework, rerun acceptance, risk review, and an
owner handoff. The separate 90-attendee change request is not implemented or
approved. No RAPPID, signature, membership, canonical operation, remote
authority, or invented runtime is created by this business-data package.
