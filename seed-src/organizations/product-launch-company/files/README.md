# The Product Launch Company — Agenda Pocket

A real, original offline demo anchors this organization seed. **All supplied
meeting data and audience hypotheses are SYNTHETIC.** No customers, public
launch, measured time savings, support operation, or generated video exists.

## Use the product

Open `demo/index.html` directly in a modern browser. No server, install, CDN,
account, or internet connection is needed. Load the synthetic example, edit
topic labels/durations/required flags, and choose **Build agenda**. Local JSON
import accepts `data/sample-agenda.json`. Export downloads a plan only when
you press **Export plan JSON**. Nothing is automatically saved or sent.

Agenda Pocket reserves all required topics and a wrap interval. Optional
topics are considered in input order, not by a hidden importance score.
Required topics never silently disappear: if they exceed the session, the
plan is blocked. This is a time-budget aid, not calendar, priority, or
facilitation software.

## Reproduce the authored checks

From `files/`, with Node.js 18 or newer (standard library only):

```sh
node --test reference/test_agenda.cjs
node --check demo/core.js
node --check demo/app.js
```

The tests cover the numerical fixtures, validation, determinism, and local
asset/static rendering boundaries. Manual browser and assistive-technology
checks have a separate protocol; a passing unit suite does not imply those
checks occurred.

The six workspaces own product, design, engineering, creative, distribution,
and customer success. Their task DAG starts with this usable reference and
ends with a conditional launch plan and feedback instrument. Source copy and
storyboard are starter material, not evidence that a launch or a video was
completed. No source file grants publication, spending, outreach, identity,
or membership authority.
