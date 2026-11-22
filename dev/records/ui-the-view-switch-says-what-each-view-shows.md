# ui-the-view-switch-says-what-each-view-shows: The view switch says what each view shows

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q03 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram toolbar

**The problem:** 'Dynamics | Blocks | Process' explain themselves only in hover titles, which a phone never shows. 'One model, read two ways' is on Guide frame 2 only.

**The change:** Visible labels: 'Dynamics · what is', 'Blocks · what is controlled', 'Process · what happened'. Keep the hover titles. At 390 px the second half may wrap under the first.

**User stories it serves:** G1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
The three toggle buttons' visible text contains 'what is', 'what is controlled' and 'what happened' at 1440 px and at 390 px.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
