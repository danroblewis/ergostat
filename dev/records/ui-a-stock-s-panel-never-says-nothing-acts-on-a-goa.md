# ui-a-stock-s-panel-never-says-nothing-acts-on-a-goa: A stock's panel never says nothing acts on a goal that has an actor

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q24 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** stock panel (Dynamics)

**The problem:** users: 'desired users = 180 (nothing in the model acts on its gap: no feedback closes it)' while Loops lists users-growing, moved by product-manager, and the stock is in 13 loops.

**The change:** The 'Desired level' row names the goal and what serves it ('goal users-growing, served by product-manager in factory'). Say 'nothing acts on its gap' only when the goal has no controller anywhere.

**User stories it serves:** B5, C3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 the users stock panel contains 'users-growing' and 'product-manager' and does not contain 'nothing in the model acts'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
