# ui-open-frames-what-was-opened-fit-includes-every-w: Open frames what was opened, Fit includes every wire, and the edge hint says which way

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q71 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Open, Into, Fit)

**The problem:** After Open the opened system lands half off-screen under a large empty area; Fit still leaves wires and labels beyond the right edge; 'More beyond the edge' does not say where; the floating toolbar covers labels.

**The change:** After Open or Into, pan and zoom so the opened system's bounds are in view (at no less than the minimum text size). Fit uses the bounds of every node, wire and label. The hint reads 'more to the right / below' and is clickable to pan there. Keep the toolbar off the drawing's bounds.

**User stories it serves:** H2, A5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797 after Open on api, api's bounding box is wholly inside the canvas viewport or a hint naming a direction is shown; after Fit on :8791 ?view=blocks&system=modelling every path's and text's bounding box is inside the viewport and no hint is shown.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
