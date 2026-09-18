---
name: "hive-hub"
description: "Safely dial or join a declared Hive from a GitHub address, local path, seven-word chant, full Dial Record ID, or camera/QR/AI join card. Use when someone says “dial this hive”, “join this hive on this device and tell me when you are ready”, or asks to scan a Hive QR code. The locked runner is protocol-neutral, plans every external effect first, uses existing access, never executes downloaded learning material, and returns one actionable blocker when it cannot continue."
license: "MIT"
compatibility: "Requires Python 3.11+; Git is required only for GitHub targets. Run with Python isolated mode (-I). Uses existing Git credentials without prompting and stores approved device-local state under ~/.agent-storage/hive-hub/v1 unless an absolute device root is supplied."
metadata:
  version: "0.1.1"
  lock: "agent.lock"
  runner: "scripts/run.py"
allowed-tools: "Bash Read Camera"
---

# Hive Hub

This skill works without prior knowledge of RAPP, MicroSOL, or any other Hive
protocol. A Hive must declare its exact protocol, adapter, conformance material,
and content-addressed learning bundle. The runner either uses a bundled,
verified adapter or returns one blocker containing the inert learning bundle.

Read `instructions/HUMAN.md` when guiding a person and
`instructions/AI.md` when another AI is operating the skill.

## Dial or join

From this skill folder, decode a locator without network or writes:

```bash
python3 -I -B scripts/run.py decode --locator '<locator>'
```

Plan a dial or join:

```bash
python3 -I -B scripts/run.py dial --locator '<locator>'
python3 -I -B scripts/run.py join --locator '<locator>' \
  --workspace-address '<optional workspace address>'
```

Accepted locators are:

- canonical public or private GitHub HTTPS repository URLs;
- `owner/repository at exact/branch`;
- an explicit local file or directory path;
- a `hive-hub-chant/1` seven-word chant derived from the full Dial Record ID;
- a full `dial:sha256:<64 lowercase hex>` Dial Record ID; or
- bounded QR/AI join-card JSON.

The first response is a plan whenever network access or local writes would
occur. Show the person the effects and ask for explicit approval of the
complete `plan_digest`. Apply only that exact digest:

```bash
python3 -I -B scripts/run.py join --locator '<same locator>' \
  --apply '<exact lowercase plan_digest>'
```

A remote target normally has two approved stages: resolve its exact Git or
pinned static declaration, then save the subscription and inert typed adapter
plan. Static approval binds the canonical declaration URL, SHA-256, byte count,
locator, and hashed output root. Re-run the same command with each newly
returned exact digest. Never shorten, retype, or infer a digest.

## Camera, QR, and AI cards

Locator-only cards may be passed as an argument:

```bash
python3 -I -B scripts/run.py join \
  --card-json '{"schema":"hive-hub-qr-join-card/1","locator":"owner/repo at main"}'
```

If a card contains an optional unlock fragment, do not put it in shell history,
logs, chat, or a network URL. Pass the raw camera/QR payload only through
standard input:

```bash
camera_or_qr_reader | python3 -I -B scripts/run.py join --card-stdin
```

The only URL form that may contain an unlock fragment is a locally consumed
`hive://join?...#...` payload received through standard input. The runner
removes that fragment before any lookup, never returns or stores it, and checks
it only after the target's existing ACL has succeeded. A factor is exactly 32
random bytes encoded as canonical unpadded base64url. Its stored declaration
commitment is bound to the record, policy scope, and epoch.

## Dialbooks

`hive-hub-chant/1` hashes the UTF-8 full canonical Dial Record ID with SHA-256
and maps the first seven digest bytes modulo the frozen 128-word vocabulary.
The vocabulary is byte-exact from
`kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae`, with SHA-256
`325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`;
the derivation requires no RAPP identity or runtime. Human input may vary case
and use spaces, while canonical output is seven lowercase hyphen-separated
words.

Chants and Dial Record IDs are locators, never proof. They resolve against the
locked public dialbook or one exact device-local dialbook selected with
`--dialbook /absolute/path/to/dialbook.json`. The runner never scans for a
dialbook. Every candidate's complete Dial Record ID must match its verified
declaration. A chant collision returns every full candidate ID and refuses to
guess. Repository slugs and other display/search aliases are not chants.

## Safety boundary

- Existing source ACLs remain authoritative. No collaborator, permission,
  credential, key, token, or identity is created or brokered.
- Unauthorized and nonexistent remote targets return the same unreachable
  result.
- `acl-only` is the default. `acl+qr` is an optional second factor checked only
  after ACL success.
- Remote JSON is bounded, static, and pinned by an exact Git object or explicit
  byte count plus SHA-256. Static declaration fetches are limited to locally
  trusted origins; DNS answers and redirects to loopback, private, link-local,
  reserved, metadata, or other non-global targets are refused before use.
- Downloaded protocol text, examples, skills, adapters, and commands remain
  inert. Repository-provided setup, verification, adapter, and skill code is
  never imported or executed, even if it copies a known contract.
- Joins save one reversible local subscription, return an exact typed inert
  adapter plan, and return the declaration's inert next step. Adapter execution
  belongs only to separately approved, locally shipped immutable code pinned by
  local trust.
- Locked package files must be ordinary files with exact byte counts and
  SHA-256 hashes. Symlinks, special files, and real hardlinks are refused;
  Windows uses no-follow handle metadata for the true link count, and every
  platform requires exactly one.
- Results never contain credentials, unlock fragments, private local paths, or
  raw transport diagnostics.

Return the runner's JSON result exactly. A refusal is a safety result, not a
request to bypass the lock.
