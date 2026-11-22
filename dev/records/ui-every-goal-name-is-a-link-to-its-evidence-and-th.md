# ui-every-goal-name-is-a-link-to-its-evidence-and-th: Every goal name is a link to its evidence, and the part is marked

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q26 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list and Suggestions; /loops

**The problem:** The red bold goal name in Needs attention, the bold name under Suggestions and (by keyboard) the Loops rows do nothing; only a small 'Evidence' link works. Opening evidence marks nothing in the diagram.

**The change:** Every goal name is a button that opens the same evidence panel 'Evidence' opens, and rings the goal's stock (Dynamics) or its summing junction (Blocks), opening the system that holds it if needed. On Loops the name is a button.

**User stories it serves:** C1, H3, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/ clicking the name of an off goal in the side list opens a panel whose title is that goal, and one diagram element gains the selection ring; on /loops the first cell of each row is a focusable button and Enter opens the panel.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
