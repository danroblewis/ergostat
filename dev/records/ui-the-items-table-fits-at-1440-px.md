# ui-the-items-table-fits-at-1440-px: The Items table fits at 1440 px

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q52 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items

**The problem:** The ticket table's 'latest', 'last' and 'in state' columns are cut at the right edge ('ergos…', 'in s') with no scroll cue; pr_url takes the width.

**The change:** Show pr_url as a short link ('PR #7'). If columns still overflow, wrap the row's secondary fields onto a second line. At phone width keep id, state and time in state.

**User stories it serves:** F1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 1440x900 on :8791/items every th's right edge is within the table container's right edge and no cell's text is clipped (scrollWidth ≤ clientWidth).

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
