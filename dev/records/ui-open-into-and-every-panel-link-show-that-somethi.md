# ui-open-into-and-every-panel-link-show-that-somethi: Open, Into and every panel link show that something is happening

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q11 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Open, Into, links that open a panel), /loops, /items

**The problem:** After Into the canvas and the side list stay fully blank for 1 to 5 s; the 'fixer' link takes 3 to 4 s with no cue; Loops and Items show only their heading while loading. All read as a crash.

**The change:** Keep the old diagram, dimmed, until the new one is ready, and draw 'Opening api…' on the canvas at once. Never blank the side list. A panel opening shows its title and 'Loading…'. Loops and Items show 'Loading…' under the heading.

**User stories it serves:** A5, H2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
300 ms after clicking Into on api (:8797) the canvas contains visible text and the side list is not empty; 300 ms after clicking the 'fixer' link in a goal's evidence the panel region contains 'fixer'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
