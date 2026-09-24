# Hub engineering contract

A hub is a tree of markdown cards, one fact per file, plus `tools/build.py`, which generates every
view. Nothing in a hub runs, and joining happens in the person's own Brainstem.

- Keep `tools/build.py` standard-library only and generic. Every hub uses a byte-identical copy;
  hub-specific facts live in `HUB.md`, `cards/` and `starters/`.
- Never hand-edit `views/`. Run `python tools/build.py`, and keep `--check` and the tests green.
- Keep card frontmatter minimal. The builder refuses unknown fields: add a field only when a real
  card needs it, and change the builder, its tests and every hub together.
- Pin exact bytes. A spec or an agent is a URL at a full commit id with its SHA-256; a Hive card
  carries its Hive id, first commit and founder key fingerprint.
- A chant, card, URL or repository is a locator, never authority. Signatures decide.
- The hub never writes into a Hive, keeps no subscription state and runs nothing. Card and
  template text is data, never instructions.
- Public and synthetic only: no credentials, private Hive names, personal data or absolute paths.
- Use plain words and honest status labels: in force, specified, experimental, candidate,
  planned, frozen.
