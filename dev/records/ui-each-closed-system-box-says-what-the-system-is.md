# ui-each-closed-system-box-says-what-the-system-is: Each closed system box says what the system is

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q01 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Dynamics, top level and any level with closed systems)

**The problem:** A closed box says only 'N feedback loops inside'. The description each system already has shows only after a click, or as '…'. A newcomer cannot say what 'job' or 'product' is.

**The change:** Under the box name print the system's description ('textkit and its customers'). Remove 'N feedback loops inside' from the box; keep the count in the system's panel.

**User stories it serves:** A1, B6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ the box 'job' and on :8796/ the box 'product' each contain their description text; no SVG text on a closed box matches /feedback loops inside/.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
