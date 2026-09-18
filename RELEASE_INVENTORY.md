# Hive Hub 0.1.0 release inventory

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
- `contracts.py`: typed closed contracts and semantic validation
- `filesystem.py`: no-follow, atomic no-replace, reversible storage
- `store.py`: separated books, registry, indexes, and local state
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

## Universal skill

- Path: `skills/hive-hub/`
- Version: `0.1.0`
- Locked, stdlib-only Python 3.11+ runner
- Cross-platform lock verification accepts file link counts `0|1` on Windows
  and exactly `1` elsewhere while rejecting real hardlinks and byte/hash drift
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
- Only real sample:
  `billwhalenmsft/softwarecoellc-vteam-hive@f66da3d879b53a439bc87de764d79f68ceec048a`

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
- public/private input isolation and private-locator/secret scan
- core CLI plus skill dial/card/join subscription end to end
- adapter optionality, chant vector/collision, and Payphone outcome tests
- clean Git worktree after the release commit
