# ui-the-lifecycle-strip-shows-the-path-taken-and-doe: The lifecycle strip shows the path taken, and does not draw alternatives as next steps

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q55 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /item/…

**The problem:** The strip draws 'done → stopped → dead' and, on a session, 'open → done → failed → lost' with arrows, as if a done item can still fail. States ahead are 1.6:1 grey.

**The change:** Draw the states this item passed through, joined by arrows, ending at its present state. Other endings sit apart with no arrow ('could also have ended: stopped, dead'), in muted text of at least 4.5:1. Final states carry a mark (a double border).

**User stories it serves:** F2, F6, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On a done ticket no arrow element lies between 'done' and 'stopped'; every state label has contrast ≥ 4.5:1 in light and dark.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
