# ui-everything-clickable-in-the-diagram-can-be-reach: Everything clickable in the diagram can be reached and acted on by keyboard

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q74 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views); side panel 'Feedback loops' rows

**The problem:** Open, Into, stocks, flows, blocks and loop markers are SVG groups with no tabindex or role; Tab skips the diagram. The side panel's loop rows are divs. A keyboard or screen-reader user cannot open a system or read a block's definition.

**The change:** Give each system box's Open and Into, each stock, flow, block and loop marker tabindex=0, role=button and an aria-label ('stock api-q0, 13, desired ≤ 20, holding'); Enter and Space do what a click does. Side-panel loop rows become buttons. Opening a panel moves focus to its heading; Escape returns focus to the part.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Using only Tab, Enter and Escape on :8791/: focus reaches 'Open' on factory and opens it; reaches a stock and opens its panel with focus on the panel heading; Escape returns focus to that stock. Every element with cursor:pointer in the svg is focusable.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
