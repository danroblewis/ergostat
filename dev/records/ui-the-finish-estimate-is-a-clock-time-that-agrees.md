# ui-the-finish-estimate-is-a-clock-time-that-agrees: The finish estimate is a clock time that agrees with the critical path

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q60 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /items Graph and Timeline (roadmap)

**The problem:** 'last of 1 epic done in about 1s (p90 1s)' appears seconds after the view, as a duration, beside 'critical path 5 items, done in about 15s'; the item page uses a third form. The Timeline lists 100+ epics oldest first, so the current one is three screens down.

**The change:** One sentence, present on first paint (or 'being worked out'): 'last epic (e100) expected 04:02, by 04:03 at worst (9 in 10)', not earlier than the critical path's end. The Timeline opens scrolled to 'now' with finished epics collapsed.

**User stories it serves:** F5, B4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8794/items?view=graph the legend contains a clock time and 'at worst'; that time is ≥ now + the critical path's remaining duration; on Timeline the 'now' line is inside the viewport at load.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
