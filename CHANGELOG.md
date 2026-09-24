# Changelog

## Target shape (experimental branch; `main` keeps the previous design)

- A hub is now a tree of markdown cards, one fact per file, plus `tools/build.py`, a
  standard-library builder that checks every card and generates `views/`: the api/v2 JSON, a
  static site that needs no JavaScript, and `chants.txt`.
- Cards: the protocols `hive-md` (experimental), `rapp-hive/1` (in force) and `rapp-hive/2`
  (frozen), and the synthetic Contoso model Hive (experimental, no live shared copy).
- Joining happens only in the person's own Brainstem, with the card's pins. The hub writes nothing
  into a Hive, keeps no subscription state and runs nothing.
- Removed the Python package and CLI, local subscriptions, join cards, bootstrap, adapters
  (including the short-lived `hive-md` pin adapter, whose checks moved into the builder), the
  generated api v1 and site, the locked Agent Skill, the RAPP Work organization seeds, the static
  build scripts and the release workflows.
- Kept the frozen `hive-hub-chant/1` vocabulary; a chant now comes from a card's SHA-256.

## 0.1.1 - 2026-09-18

- Added protocol-neutral `hive-hub-chant/1` with deterministic seven-word
  locators derived from a complete `dial:sha256:` Dial Record ID.
- Corrected the public sample chant while preserving the original 0.1.0 source
  URLs, release object, schemas, and device-local dialbook compatibility.
- Added a versioned `hive-hub-dialbook/2` profile that separates aliases from
  chants and cryptographically binds locator and declaration references.

## 0.1.0 - 2026-09-18

- Introduced the typed, standard-library-only `hive_hub` package and
  `hive-hub` CLI.
- Added closed canonical contracts and packaged JSON Schemas.
- Added separated local/public/private dialbooks and collision-safe dialing.
- Added inert protocol learning, adapter registration, join cards,
  plan/apply/revert subscriptions, and one-card bootstrap.
- Added mandatory ACL semantics and optional scope/epoch-bound `acl+qr`.
- Added bounded no-follow storage, duplicate-key refusal, atomic no-replace
  writes, clean JSON errors, and zero-network tests.
- Integrated six exact-fingerprint stdlib adapters through a lazy, optional
  core bridge and plan-first CLI registration.
- Added the locked universal Agent Skill with exact core camera-AI card support
  and repository-neutral verified join-contract detection.
- Added the public-only deterministic static API, Pages join surface, release
  metadata, published core schemas, dual QR cards, and append-only receipts.
- Added deterministic source inventory, privacy scanning, packaging checks, and
  Python/Node CI matrices.
- Hardened Windows link verification with no-follow Win32 handle metadata so
  ordinary files report one link and hardlinks fail closed.
