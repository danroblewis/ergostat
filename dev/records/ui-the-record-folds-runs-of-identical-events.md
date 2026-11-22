# ui-the-record-folds-runs-of-identical-events: The Record folds runs of identical events

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q33 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record

**The problem:** On ticket-factory the Record is mostly 'auxiliary.set team-reviewing teammate {"value":0}' every 5 s, which buries the one-a-minute 'block.commanded fixer'.

**The change:** Consecutive events with the same type, source, item and data become one row with '×N' and the first and last time; clicking it lists them.

**User stories it serves:** C5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/record no two adjacent rows have identical type, source and data text; a row containing '×' followed by a number exists.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
