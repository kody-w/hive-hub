# ORDER — make the front door read like a product, not a specification

## Intent

The cold-start plumbing is being fixed in a separate pass. This order is about
everything a newcomer SEES. Today the repo presents as a specification: a
503-line README that opens with closed-contract guarantees, four reference
docs and no quickstart, and a hub page whose headline sells ten downloadable
org seeds while the genuinely novel thing — a seven-word chant you can say out
loud to locate a Hive — sits below the fold.

A person who lands here should understand what a Hive is and be inside one in
under a minute. Nothing in this order changes behaviour, contracts, hashes, or
the wire format. It is copy, structure, docs, and error messages.

## Inputs to study

- `README.md` — the PyPI project page and the repo front door.
- `docs/CLI.md`, `docs/CONTRACTS.md`, `docs/SECURITY.md`, `docs/ORGANIZATION_SEEDS.md`.
- `scripts/lib/render.mjs` — `renderHomeHtml`, `renderJoinHtml`, `renderHubCss`.
- `src/hive_hub/errors.py` and every `ValidationError` / `unreachable` path in
  `src/hive_hub/store.py` and `src/hive_hub/cli.py`.
- The cold-start commands as they exist on this branch after the prior pass —
  read them and use the real syntax, do not invent it.

## Rules / do-not-touch

- **Behaviour is frozen.** No contract changes, no new fields, no changed
  hashes, no changed chants, no new CLI verbs. If you believe one is needed,
  put it in flags/surprises instead of doing it.
- `src/` edits are limited to **error message text and the `hint` they carry**.
  Do not change control flow, what is raised, or any exit code.
- Do not touch `api/` or `hub/` output by hand — change `scripts/lib/render.mjs`
  and regenerate with `npm run build`.
- Do not touch `adapters/`, `skills/`, `examples/`, `tests/` except to add
  tests for anything you add.
- Do not weaken any security claim to make the copy friendlier. Every claim in
  the README must remain literally true of the code; if a sentence reads well
  but is not exactly true, cut it.
- Do not push, tag, or open a PR. Commit to the current branch only.

## The work

**0. A way back to the site, at the very top of the README.**
Most people who land on the GitHub repo page did not mean to end up looking at
source code. The FIRST thing in `README.md`, above the title and above every
badge, is a plain, prominent link back to https://kody-w.github.io/hive-hub/
with a few words telling a non-technical visitor that the site is where they
actually want to be. One line, no jargon, impossible to miss. Do the same at
the top of `docs/QUICKSTART.md`.

**1. README, restructured for a reader who has never heard of this.**
Lead with what a Hive is and why a chant matters, in plain language, in under
120 words. Then a quickstart that runs from a bare `pip install` and actually
reaches a live Hive, copied verbatim from commands you have RUN. Then the
guarantees — they are the project's real distinction and they stay, but they
belong below the thing they protect, not above it. Keep every existing
technical claim; move and compress, do not delete substance.

**2. `docs/QUICKSTART.md`** — the sixty-second path, start to joined, with the
exact output a reader should expect at each step so they can tell whether it
worked. Link it from the README and from `docs/CLI.md`.

**3. The hub page leads with the dial.** In `renderHomeHtml`: the hero is the
live public laboratory Hive and its chant, big enough to read across a room,
with the one command that gets you in. The ten organization seeds stay — they
are good — but as the second section, not the headline. Keep the existing CSS
vocabulary and the accessibility and no-external-resource guarantees that the
static-surface test enforces.

**4. Error messages a person can act on.** Every failure a newcomer can
plausibly hit should say what to try next. `{"status":"unreachable"}` is
correct and tells a human nothing — it is also deliberately identical across
private-absence, failed-ACL, missing-policy and wrong-QR-factor, and that
indistinguishability is a SECURITY PROPERTY you must not break. So: do not
differentiate it. Instead add a neutral, constant `hint` that is the same in
every one of those cases, pointing at how to supply a locator or source. Add a
test asserting the four cases remain byte-identical to each other.

## Acceptance checks — run these yourself, paste verbatim output

```bash
npm run verify
PYTHONPATH=src:. python3 -B -m unittest discover -s tests -t .

# The quickstart is real: run every command in docs/QUICKSTART.md, in order,
# in a fresh venv from a built wheel, in a directory with no checkout.
# Paste the actual session.

# The four unreachable cases are still byte-identical.
```

Then read the rendered hub page yourself — build the site, serve it, and
describe what the hero actually looks like at 1280px and at 390px wide. If you
cannot see it, say so rather than asserting it looks right.

## Done when

Committed in small readable commits, acceptance output pasted, ending with a
report and a **flags / surprises** section. In that section I specifically want:
anything in the README you believe is no longer true of the code, and any place
the friendly copy and the precise claim pulled against each other.

## FILE OWNERSHIP — a concurrent job is running

Two other muscle jobs are working at the same time. You own EXACTLY these
paths and must not create, edit, or delete anything else:

- `README.md`
- `docs/` (including the new `docs/QUICKSTART.md`)
- `scripts/lib/render.mjs`
- `hub/` and `api/` ONLY as regenerated output of `npm run build`

You do NOT own and must not touch: anything under `src/`, `tests/`,
`adapters/`, `skills/`, `examples/`, `scripts/` other than `render.mjs`,
`.github/`, `pyproject.toml`, `package.json`.

Item 4 of this order (error messages) is REMOVED from your scope — it lives in
`src/` and another job owns it. Skip it entirely.

A concurrent job is fixing CI on the branch you started from, so your
`npm run verify` may show failures in `scripts/smoke-http.mjs` and in
`tests/test_remote_dial.py` that are NOT yours. Report them, do not fix them,
and do not let them stop your own work.
