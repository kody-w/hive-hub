# Support starter

**SYNTHETIC examples. No staffed support operation or response SLA is promised.**

## Quickstart

Open `demo/index.html`, choose **Load synthetic example**, and build. Edit a
topic or session length, then build again. The previous export is disabled
when inputs change. Import expects the source agenda schema shown in
`data/sample-agenda.json`, not an exported result report.

## Troubleshooting tree

- **I see a blocked plan.** Required minutes exceed duration minus wrap.
  Increase duration, reduce explicitly edited estimates, or deliberately
  change requirements. The app must not decide what is no longer required.
- **An optional topic disappeared from the schedule.** It is listed under
  “Not scheduled.” Optional topics are considered in entry order; this is
  not an importance optimizer.
- **My JSON will not import.** Check complete JSON, unique lowercase topic
  IDs, boolean required fields, integer durations, and the 64 KiB limit.
  The previous editor is retained after a failed import.
- **Where did my draft go after reload?** There is no automatic persistence.
  Export is explicit. Exported plans are reports, not editable source files.
- **Can I use dates or multiple time zones?** No. The reference works with
  one same-day clock and ends no later than 24:00.
- **Can support inspect a private meeting?** Reproduce with the synthetic
  sample or invented topic labels first. Do not request personal agenda text.

## Minimal issue intake

Collect: browser family/version (optional), action attempted, expected versus
observed behavior, synthetic reproduction, and whether it occurs offline.
Ask separately for consent before retaining any shared material. No analytics
are embedded and no actual responses are supplied.

Escalate numerical disagreement to Engineering, confusing decisions to
Design/Product, and promise or support-boundary changes to the owner. Do not
describe local correctness as customer validation.
