# Interaction and visual specification

**SYNTHETIC reference design; accessibility certification is not claimed.**

Use a calm high-contrast layout: near-white canvas, dark ink, teal primary
action, amber blocked-state border. Never rely on color to distinguish a
required topic or a blocked result. Text labels and explicit required flags
carry the meaning. A responsive two-column layout becomes one column on
narrow screens; topic controls remain in document reading order.

## Interaction contract

1. Load the reference sample with visible SYNTHETIC label.
2. Edit title, start, session duration, wrap, and topic rows using ordinary
   labeled inputs. Each row has a label, whole-minute duration, required
   checkbox, and a remove button.
3. Add a topic without erasing existing rows. Removal and edits invalidate
   the old export so stale results are not presented as current.
4. Build the agenda. Announce errors and move focus to the error summary.
   Display required minutes, scheduled minutes, slack, and wrap explicitly.
5. Import only a user-selected small JSON file. Validate before replacing
   the existing editor. A failed import must preserve the existing work.
6. Export only a current successful calculation; a blocked result may be
   exported as an explicitly blocked analysis, never as a feasible agenda.

## Content safety and local operation

Render topic labels through `textContent`, not HTML parsing. No imported
markup becomes an element or script. The browser does not fetch sample JSON;
the same original sample is bundled in the core so file-open works offline.
Tests compare that embedded sample to the structured source fixture.

No automatic persistence is provided. Reloading discards unsaved edits.
The support kit must explain this clearly. Browser extensions or operating
system behavior are outside the application's no-network design boundary;
do not make universal confidentiality guarantees.
