# Mosslight Courier rules and production baseline

Original authored game design; all business and playtest context is SYNTHETIC.

## Deterministic contract

The board is nine columns by seven rows. A courier begins at D with one cell,
zero successful actions, no lit beacons, and bridge beat 1. Each board has
exactly one depot and three beacons. Each legal movement or wait advances
the action count by one. Bridge availability is evaluated **before** the action:
`turn % 4 < 2` means open. Walls and entry into a closed bridge block movement
and consume no action. Leaving or waiting on a bridge is legal when it closes.

Entering an unlit beacon with a cell lights it and empties the carrier.
Entering D empty reloads automatically. Lit beacons remain traversable.
The third delivery wins. Further move/wait actions do nothing after a win;
undo and restart remain available. Undo restores position, count, carrying,
and delivered set, including undoing a win. The latest 256 successful actions
are retained; restart or changing boards clears history.

## Specific first-shift production question

Can a player predict a bridge entry from the next-action text without guessing?
The synthetic records suggest five bridge stalls, but do not demonstrate real
usability. The work is an onboarding/readability pass, not a new-mechanics
prototype. Preserve the authored layouts and engine semantics.

State-example review pairs:

| Before | Action | After |
|---|---|---|
| Adjacent to bridge; turn 1 | Enter bridge | Legal; turn 2; now closed under courier |
| On bridge; turn 2 | Leave to path | Legal; turn 3 |
| Adjacent to bridge; turn 2 | Enter bridge | Blocked; still turn 2 |
| Adjacent to bridge; turn 3 | Wait | Turn 4; next action opens |
| Empty at a path beside D | Enter D | Carrying one; one action spent |
| Carrying at last unlit beacon's neighbor | Enter beacon | All lit; win |

There is no randomness, timer, score leaderboard, combat, copied character,
external content, or hidden information. The only efficiency measure is
successful action count; undo is intentional, not a competitive exploit.
