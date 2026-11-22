# ui-no-leftover-in-a-panel: No leftover '…' in a panel

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q04 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side panel (system panel, stock panel, loop panel)

**The problem:** The system panel shows a lone '…' under its title; the loop panel shows 'When it drives the behaviour …' for good; both read as a stuck load.

**The change:** Show the description, or nothing. While a value is being worked out say 'being worked out'; when it cannot be, say why ('no loop is dominant in this window').

**User stories it serves:** A4, G4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
After 10 s on :8796, clicking the product box, the users stock and marker R2: no element in the side panel has text equal to '…' or ending in ' …'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
