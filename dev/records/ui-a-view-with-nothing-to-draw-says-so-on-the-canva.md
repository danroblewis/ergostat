# ui-a-view-with-nothing-to-draw-says-so-on-the-canva: A view with nothing to draw says so on the canvas

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q10 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram?view=process (big); /diagram top level of big

**The problem:** The Process view on big is a blank canvas: its empty-state text sits at y=900, below the canvas. The line 'No flows at this level: what crosses between these systems is information only' is drawn at y=−14 and never seen.

**The change:** Centre the empty-state text in the canvas at every width, with the reason and where to look instead ('No kinds of item in big: its parts are counted by sensors. See Dynamics.'). Draw the 'No flows at this level' line under the boxes.

**User stories it serves:** A5, H1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/diagram?view=process at 1440x900 an element containing 'No kinds of item' lies wholly inside the canvas's bounding box; on :8797/ the text 'No flows at this level' has y within the viewport.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
