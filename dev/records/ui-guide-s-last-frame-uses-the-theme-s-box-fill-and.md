# ui-guide-s-last-frame-uses-the-theme-s-box-fill-and: Guide's last frame uses the theme's box fill, and says it is loading

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q06 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /guide?frame=12

**The problem:** In light mode the system dynamics thumbnail draws boxes as solid black with unreadable text; arriving by the arrow, the frame is blank for 1 to 2 s with no text.

**The change:** Draw the thumbnail with the page's theme tokens (the same fill as the live diagram). Until both thumbnails have rendered show 'Drawing your system…' on the stage.

**User stories it serves:** A3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At /guide?frame=12 in light mode every system-box rect in the left thumbnail has a computed fill equal to the live diagram's box fill, and its text contrast is at least 4.5:1; 200 ms after pressing → from frame 12 the stage contains visible text.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
