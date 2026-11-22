# ui-the-headline-counts-the-system-s-goals-and-the-m: The headline counts the system's goals, and the model's upkeep apart

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q14 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** header on all pages; project switcher

**The problem:** '2 loops off' in red on software-factory and the-job is entirely modelling's own two goals; every demo is permanently red, so red stops meaning anything.

**The change:** Header reads '0 goals off · model upkeep 2' (the second part in the muted colour, not red). The switcher uses the same definition, and states unknown goals separately ('7 off, 1 unknown') instead of adding them.

**User stories it serves:** A2, B2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796 with only requests-handled and model-fits off the header's first figure is 0 and is not red, and the text 'model upkeep 2' is present; the switcher entry for a demo read from another demo shows the same first figure as that demo's own header at that moment.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
