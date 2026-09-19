# Hive Hub 0.1.1 release inventory

## Python distribution

- Project/distribution: `hive-hub`
- Import: `hive_hub`
- Console command: `hive-hub`
- Runtime: Python `>=3.10`
- Runtime dependencies: none
- Build artifacts: wheel and source distribution
- Typed marker: `hive_hub/py.typed`
- Optional adapter import: `adapters`
- Adapter runtime dependencies: none
- Importing `hive_hub` does not import or discover adapters

## Canonical schema files

- `adapter-plan.schema.json`
- `adapter-registration.schema.json`
- `adapter-registration-receipt.schema.json`
- `ai-join-card.schema.json`
- `bootstrap-result.schema.json`
- `chant-locator.schema.json`
- `conformance-contract.schema.json`
- `dial-record.schema.json`
- `learning-bundle.schema.json`
- `local-subscription.schema.json`
- `local-subscription-plan.schema.json`
- `private-access-policy.schema.json`
- `private-dialbook-index.schema.json`
- `protocol-declaration.schema.json`
- `protocol-fingerprint.schema.json`
- `public-dialbook-index.schema.json`

## Core modules

- `canonical.py`: bounded duplicate-safe JSON and SHA-256 addresses
- `chant.py`: protocol-neutral `hive-hub-chant/1` derivation, parsing,
  vocabulary provenance, and full-ID verification
- `contracts.py`: typed closed contracts and semantic validation
- `_windows_file.py`: no-follow Win32 handle metadata and true link counts
- `filesystem.py`: no-follow, atomic no-replace, reversible storage
- `store.py`: separated books, registry, indexes, local state, and explicitly
  approved bounded public snapshot fetching
- `published.py`: closed core-record projection and inert dependency validation
- `hub.py`: protocol learning, registration, dial, join, and bootstrap
- `schema_catalog.py`: bundled Draft 2020-12 schema catalog
- `cli.py`: canonical JSON command surface and sanitized errors
- `adapter_runtime.py`: lazy mapping from exact adapter declarations to core
  contracts and plan-first local registration

## Integrated adapter package

- GitHub repository locator/probe
- local filesystem workspace
- optional installed RAPP Work/Hive delegate
- collision-preserving seven-word RAPPID chant
- Payphone `connected|unreachable` resolution
- inert historical Hub inspection

## Generic chant contract

- Protocol: `hive-hub-chant/1`
- Input: full canonical Dial Record ID
- Derivation: SHA-256 over the UTF-8 full ID; first seven digest bytes modulo
  the frozen 128-word vocabulary
- Vocabulary SHA-256:
  `325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`
- Provenance:
  `kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae`
- Runtime/identity dependency on RAPP: none
- Semantics: collisionable candidate locator only; complete Dial Record ID
  verification is mandatory

## Universal skill

- Path: `skills/hive-hub/`
- Version: `0.1.1`
- Locked, stdlib-only Python 3.11+ runner
- Cross-platform lock verification uses no-follow Win32 handle metadata on
  Windows and `st_nlink == 1` on POSIX while rejecting real hardlinks and
  byte/hash drift
- Accepts the core `ai-join-card` camera contract
- Selects executable current-main behavior only by an exact verified join
  contract, never by repository name
- Copied-folder proof runs without repository context

## Static API and Pages

- Public source root: `public-src/`
- Explicit public manifest: `public-manifest.json`
- API: `/api/hive-hub/v1/`
- Integrated release: `/api/hive-hub/v1/release.json`
- Published core schemas: `/api/hive-hub/v1/core-schemas/`
- Human surface: `/hub/`
- Browser-free AI instructions: `/hub/join/ai.json` and `/llms.txt`
- Ten public RAPP Work organization starters:
  `/api/hive-hub/v1/organization-seeds.json`
- Individual seed pages: `/hub/seeds/<slug>/`
- Content-addressed seed JSON and deterministic ZIP downloads:
  `/api/hive-hub/v1/seeds/`
- Native initialization conformance: ten pointer-only Organizations and all
  declared team/case Workspaces, exercised only in temporary test fixtures.
- Seeds contain no live identities, keys, memberships, signed activation, or
  fabricated completed-work evidence. Consumers initialize their own state.
- Explicitly public onboarding sample:
  `kody-w/hive-hub@8e9ee55a7eb9fe4b4aaa084290e1916c0edcade9`
- Sample Dial Record ID:
  `dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32`
- Sample chant: `juniper-quartz-harbor-birch-cobalt-nook-flint`
- Display/search alias only: `hive-hub-public-lab`
- A new public-lab receipt ledger contains no dark-door locators.
- Exact-manifest privacy withdrawals remove superseded receipt sources and
  generated receipt URLs instead of republishing private metadata.
- Removed live projections do not imply deletion of prior Git history or caches.

## Deterministic source inventory

- Generator: `scripts/build_release_manifest.py`
- Manifest: `release/release-manifest.json`
- Every included path has an exact byte count and SHA-256.
- `inventory_sha256` binds the ordered file inventory.
- `.github/workflows/ci.yml` gates Python 3.10/3.11/3.14, skill
  Python 3.11/3.14, Node 20/22, static generation, privacy, and packaging.

## Required release gates

- Unit tests on every available supported interpreter (3.10, 3.11, 3.14)
- Ruff
- strict mypy
- wheel and sdist build
- isolated wheel install
- import, version, CLI, metadata, schema-data, and zero-dependency verification
- deterministic static rebuild and QR SVG validation
- all ten seed file inventories, exact ZIP bytes, task ownership/dependencies,
  and native RAPP Work SDK initialization
- public/private input isolation and private-locator/secret scan
- core CLI plus skill dial/card/join subscription end to end
- adapter optionality, chant vector/collision, and Payphone outcome tests
- clean Git worktree after the release commit
