# Product brief: Agenda Pocket

**SYNTHETIC product scenario and audience assumptions.**

Problem hypothesis: people drafting a small meeting agenda can see a total
duration yet still lose required decisions when optional topics crowd it out.
Agenda Pocket makes the tradeoff explicit before the meeting.

## What is real in this seed

- An editable local browser demo and reusable pure JavaScript planning core.
- Local JSON import, explicit JSON export, input validation, and visible
  ready/blocked outcomes.
- Exact reproducible numerical acceptance fixtures.

## Reference behavior

The sample starts at 09:00 for 60 minutes and reserves five minutes at the end
for wrap. Topics sum to 68 minutes, including 35 required minutes. The planner
reserves required time before admitting optional topics. It schedules 53 topic
minutes, skips the 15-minute optional template demo, and leaves two minutes
of slack before the 09:55 wrap.

The algorithm is deliberately simple: retain original order, preserve
required topics, and greedily admit optional topics if all remaining required
time still fits. It does not find the most valuable combination, infer
priorities, split topics, or shorten people's contributions.

## Scope and disconfirmation

Hypothesized audience: an individual drafting a short agenda from a local
list. No research confirms that audience. Disconfirm the interaction if an
authorized participant cannot explain why an optional topic was omitted or
mistakes a blocked plan for a feasible one after a short walkthrough.

Whole minutes only, up to 50 topics, 1–120 minutes each, sessions of 1–480
minutes ending no later than midnight. No time zones, dates, calendar
connections, collaboration, storage, telemetry, AI, reminders, or account
system. A browser file-open demo is not yet a maintained commercial service.
