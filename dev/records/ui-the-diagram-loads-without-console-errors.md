# ui-the-diagram-loads-without-console-errors: The diagram loads without console errors

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q81 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views, all demos)

**The problem:** Every diagram load logs 'xOffset value … in ShapeConnectionPin constructor greater than shape width'; some log 'ELK failed … reading Sg', after which a fallback layout may explain some overlaps.

**The change:** Clamp the pin offset to the shape width (an off-by-one at the right edge). Find the input that makes ELK throw and fix it or report the fallback on the page ('simplified layout').

**User stories it serves:** G3, G5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Loading /diagram in Dynamics, Blocks and Process on all six demos, and Into each system, produces no console error or warning from the layout.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
