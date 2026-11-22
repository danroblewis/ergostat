# ui-on-a-phone-the-diagram-opens-fitted-to-the-scree: On a phone the diagram opens fitted to the screen

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q73 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram at 390 px

**The problem:** At 390 px the canvas is blank on the-job (neither box in view), shows part of one box on software-factory, and opens mid-drawing inside a system.

**The change:** On load and on every change of view at narrow width, fit the drawing to the canvas (down to the minimum text size, then centred on the first off part with a direction hint).

**User stories it serves:** A1, H4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 390x844 on :8792/ and :8796/ at least one whole system box is inside the canvas viewport at load; on :8796 ?system=product the stock 'users' or a direction hint is visible.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
