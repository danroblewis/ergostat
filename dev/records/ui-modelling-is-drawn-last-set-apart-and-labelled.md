# ui-modelling-is-drawn-last-set-apart-and-labelled: modelling is drawn last, set apart and labelled

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q13 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram top level (Dynamics and Blocks)

**The problem:** In every demo ergostat's model of its own upkeep is the top-left box, read first, unexplained and unconnected. A newcomer concludes the product is about itself.

**The change:** Lay modelling out last (bottom right), with a dashed outline and the line 'ergostat's upkeep of this model, not the system'. Same place in Blocks, below a thin rule.

**User stories it serves:** A2, B6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ and :8797/ in both views the modelling box's top-left corner is below or right of every other system box, its outline has a stroke-dasharray, and it contains the words 'upkeep of this model'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
