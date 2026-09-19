# Mosslight Courier — independent studio seed

All production/client/research data here is **SYNTHETIC**, authored for this
public seed. The original game is real playable source; its fictional studio
has not shipped a release or observed any players.

## Play now, offline

Open `game/index.html` directly in a current browser. No server, install,
account, CDN, network, analytics, or saved data is used.

- Focus the board with Tab or the **Focus board** button.
- Arrows / WASD: one tile per press. Space: wait one beat.
- U / Backspace: undo a successful action. R: restart this board.
- Carry one glow cell from D to each unlit beacon ○. Return to D to reload.
- Bridges admit entry on beats 1–2 of a repeating four-beat cycle. Blocked
  moves cost nothing. You can leave a bridge even when it closes beneath you.
- Clear all three beacons to win. The board selector offers three original
  puzzles. Sound is optional and synthesized locally after opt-in.

## Reproduce the reference

From this package's `files/` directory:

```text
node tests/game.test.js
python3 -I -B tools/feedback_report.py --self-test
python3 -I -B tools/feedback_report.py
```

Tests exercise the same engine and real keyboard/click handlers used by the
browser, including a breadth-first solver for every board and a minimal DOM
test double. The runner works under both CommonJS and ES-module host projects
without a package manifest. It does **not** claim a real browser, screen-reader,
or real-player test. The feedback report reads the eight authored
records: five completions, five bridge stalls, three undo discoveries, and
54.4 mean actions among completed sessions.

## Start the organization

The blueprint's seven teams own a two-day bridge-onboarding revision. Start
with the production scope and synthetic-feedback baseline, then branch into
design, art, audio, implementation, QA, and a prospective research plan.
Reference files are inputs, not completed task outputs.

Current limitations: three fixed boards, no persistence, no touch swipe
gesture, no localization, a bounded 256-action undo history, and only simple
tones. Direction buttons also work by touch/click. Screen-reader play needs
manual review: the board exposes tile labels and live status, but this is not
a claim of full accessibility conformance. There is no timer, enemy, monetization,
multiplayer, external telemetry, or production RAPP runtime. Independent
organizations are discovery-only candidates; external effects require approval.
