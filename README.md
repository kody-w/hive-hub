# Hive Hub

**`main` keeps the previous design; this branch is the target shape.** On `main`, Hive Hub is a
Python package with a CLI, local subscriptions, join cards and adapters. Here it is a tree of
markdown cards and one standard-library builder, and nothing else.

A hub is a tree of markdown cards, one fact per file, plus a builder that generates every view.
Reorganizing the hub means moving card files. Nothing in a hub runs, and joining happens in your
own Brainstem. The RAPP hub (`kody-w/rapp-hive-hub`) takes the same shape with a byte-identical
builder.

```text
HUB.md                    what this hub is, who curates it, how to submit a card, where it fits
cards/protocols/<id>.md   one card per Hive protocol
cards/hives/<slug>.md     one card per Hive
cards/orgs/<slug>.md      one card per organization (optional in this hub)
tools/build.py            standard library only; builds views/; --check compares
views/                    GENERATED: api/v2/, site/ and chants.txt
llms.txt                  a short entry for AI apps
tests/test_build.py       the builder's tests
```

## The cards

| Card | Status |
| --- | --- |
| [`hive-md`](cards/protocols/hive-md.md): the Hive folder convention | experimental |
| [`rapp-hive/1`](cards/protocols/rapp-hive/1.md): RAPP Private Hive | in force |
| [`rapp-hive/2`](cards/protocols/rapp-hive/2.md): frozen research record | frozen |
| [`contoso-model-hive`](cards/hives/contoso-model-hive.md): a synthetic model Hive with no live shared copy | experimental |

## Build and check

```bash
python tools/build.py            # check every card and write views/
python tools/build.py --check    # rebuild in memory and compare with views/ byte for byte
python -m unittest discover -s tests
```

Never edit `views/` by hand. CI runs the check and the tests on Linux, macOS and Windows.

## Card fields

Each card is `---`, one `key: value` line per field, `---`, a blank line and a short body. The
builder refuses unknown fields, missing pins, commit ids that are not full, bad key fingerprints,
duplicate slugs, credentials in URLs and absolute paths.

| Card | Fields |
| --- | --- |
| `card: protocol` | `id`, `name`, `status`, `spec` (a URL at a full commit id) and `spec_sha256`; optional `checker` and `checker_sha256`, `agent` and `agent_sha256` |
| `card: hive` | `name`, `protocol`, `status`, `hive`, `root`, `founder`, `channel`; optional `public_copy`, `address` and `org`. A `planned` Hive may omit all three pins |
| `card: organization` | `name`, `status`, `hive` (a hive slug or `template`); optional `starter` |
| `card: starter` | `name`, `status`, `template` (`starters/<folder>/`), `org` |

Statuses are `in force`, `specified`, `experimental`, `candidate`, `planned` and `frozen`;
protocols do not use `planned`. A card's sha256 is the SHA-256 of its file, and its chant is seven
words from the first seven bytes of that digest, over the frozen `hive-hub-chant/1` vocabulary. A
chant is a locator, never authority; collisions are listed in `views/chants.txt`.

## Join

1. Dial a chant from `views/chants.txt`, or open a card.
2. Check the card's sha256 against `views/api/v2/index.json`.
3. Give the card to your Brainstem. Its Hive agent joins with the card's `address`, `hive`,
   `root` and `founder`: it clones the Hive, verifies the root and the founder fingerprint, writes
   one SSH-signed request file, and sends it the way the card's `channel` says.

The hub never writes into a Hive, keeps no subscription state and runs nothing. To pull a card or
a starter down, use a read-only reference (the Hive agent's `reference`), `npx degit` or a ZIP.

## Removed on this branch

The Python package and CLI, local subscriptions, join cards, bootstrap, adapters, the generated
api v1 and site, the locked Agent Skill, the RAPP Work organization seeds, the static build
scripts and the release workflows. The frozen chant vocabulary lives on in `tools/build.py`.
