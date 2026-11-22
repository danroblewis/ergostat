# ui-the-blocks-legend-defines-every-symbol-and-a-nam: The Blocks legend defines every symbol, and a name is printed once

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q68 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Blocks 'How to read it'; subsystem blocks

**The problem:** 'Q' and the '3×1' dimensions are never defined; Q is bold on one level and italic on another; an opened subsystem reads 'Q_service  service'.

**The change:** The legend adds the subsystem symbol in use and 'p×m: outputs × inputs (disturbances counted)'. One typeface for the letter at every level. Drop the repeated plain name beside the symbol.

**User stories it serves:** G6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 ?view=blocks the legend contains '×' with the words 'outputs' and 'inputs' and defines the subsystem letter shown; no block contains its system's name twice; the letter's font-style and weight are the same at top level and inside.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
