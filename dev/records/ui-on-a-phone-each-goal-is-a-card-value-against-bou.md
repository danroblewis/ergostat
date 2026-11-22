# ui-on-a-phone-each-goal-is-a-card-value-against-bou: On a phone each goal is a card: value against bound, and how long off

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q72 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /loops at ≤ 760 px

**The problem:** The table is 943 px wide in 358 px: loop, status and holds show; now, setpoint, error and time off are off to the right with no cue. 'Time off' is a share of the window, not how long the goal has been off.

**The change:** Below 760 px each row is a two-line card: 'requests-handled · off' then '36 against ≤ 0 · off 36m · usually back in 30s'. Off goals first. No sideways scroll.

**User stories it serves:** H4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 390x844 on :8791/loops, in light and dark, each off goal's card shows its value, its bound and a duration within the viewport's width; the page's scrollWidth equals its clientWidth.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
