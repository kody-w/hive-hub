# Acceptance protocol

**SYNTHETIC fixtures; expected checks, not fabricated observations.**

## Automated

Run the Node test file and both syntax checks from the README. The structured
cases cover a normal sample, a required-only fit, one-minute overload, all
topics required, zero wrap, and end-of-day bounds. Additional tests cover
duplicates, invalid integer/boolean types, missing fields, immutability,
determinism, imported literal text, local assets, and safe text rendering.

The normal sample must schedule `welcome`, `stock-review`, `decision`,
`risk-check`, and `roundup`; `template-demo` remains unscheduled. Topic total
53 + slack 2 + wrap 5 = session 60. A blocked plan schedules zero topics and
does not silently label required topics optional.

## Manual browser protocol — record actual observations separately

| ID | Action | Reviewable criterion |
|---|---|---|
| manual-offline | Open index.html with networking unavailable | All styles and behavior load; no network is required |
| manual-keyboard | Navigate all fields and build with keyboard | Focus visible; field labels and order understandable |
| manual-blocked | Change duration to 39 and build | Blocked explanation states one required minute over capacity |
| manual-stale | Edit any field after a result | Export disables until a new calculation |
| manual-import | Import the supplied source agenda | Editor updates; result matches sample |
| manual-invalid-import | Choose invalid JSON | Error receives focus; existing editor remains intact |
| manual-export | Explicitly export a ready and a blocked result | Report contains matching status and no surprise network activity |
| manual-reader | Use an available screen reader | Labels, errors, state, schedule headers, and required flags are understandable |
| manual-narrow | Inspect at 320 CSS pixels and 200% zoom | Content remains readable and controls usable |

Record browser/platform, criterion, actual result, and pass/fail/not-observed.
Automated static checks cannot pass `manual-reader` or `manual-narrow`. No
absolute privacy, accessibility, usability, or business-outcome guarantee
follows from this protocol.
