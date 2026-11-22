# ui-check-and-the-model-page-say-each-thing-once-in: Check and the Model page say each thing once, in a table

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q78 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /check, /model

**The problem:** Check is 17 run-on sentences, 13 of them the same warning with different numbers, then 30 lines of 11 px grey prose joined by semicolons. Model repeats 'an integrator, from the model / its dead time: a step of u, or a step test' on nearly every row; its 'process, controller, scope' links are href='#' and land on an arbitrary place with every system open.

**The change:** Check: one table per kind of warning (part, R² or 'never moved', scaled error, points), sorted worst first, the advice once above it, each part a link to the diagram; notes as a list at body size. Model: group rows with the same identification ('12 loops: an integrator, not yet tested'); each link opens that loop's panel with its system framed.

**User stories it serves:** C6, G7

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/check no warning sentence longer than 80 characters occurs more than once; there is a table whose header includes 'R²'; on /model clicking 'process' for located-worked changes the URL to that loop's system and opens a panel whose title contains its process.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
