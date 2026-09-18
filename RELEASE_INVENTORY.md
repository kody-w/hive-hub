# Hive Hub 0.1.0 release inventory

## Distribution

- Project/distribution: `hive-hub`
- Import: `hive_hub`
- Console command: `hive-hub`
- Runtime: Python `>=3.10`
- Runtime dependencies: none
- Build artifacts: wheel and source distribution
- Typed marker: `hive_hub/py.typed`

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

## Required release gates

- Unit tests on every available supported interpreter (3.10, 3.11, 3.14)
- Ruff
- strict mypy
- wheel and sdist build
- isolated wheel install
- import, version, CLI, metadata, schema-data, and zero-dependency verification
- clean Git worktree after the release commit
