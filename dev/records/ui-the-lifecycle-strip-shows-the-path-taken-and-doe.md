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

## Where it stopped

Built, round 1. The strip on /item/… draws the states the item's moves passed through (repeats in a row folded), joined by arrows, ending at its present state. A done item's other endings sit apart, with no arrow, under "could also have ended:"; an unfinished item's other states sit apart under "its other states:". Both are in --muted (5.2:1 light). Endings carry a 3px double border. About 13 net lines outside tests.

Choices made alone, each easy to undo:
- A kind declares no final states, so "an ending" is what the process map already counts as finished (`process._done`: `messages: {done:}` if declared, else the states after the first that no item has left, never `leased`). The item API (`ergostat/web/server.py`) adds this to `kind_of` as `final`. On a young record some states not yet left count as endings; the process map shares that limit.
- An unfinished item lists its unvisited states apart, with no arrow, instead of hiding them, so the page still names every state of its kind.

Acceptance test: tests/test_items_page.py::test_the_lifecycle_strip_draws_the_path_taken_and_sets_the_other_endings_apart (a done session in light and dark: the path is exactly open → done, no arrow among the other endings, endings double-bordered, every label at least 4.5:1). Seen to fail with each of two breaks: the old all-states strip (extra arrows), and the alternatives set in --line-strong (1.63:1).

Run: tests/test_items_page.py with Playwright (22 passed, none skipped); tests/test_page_refresh.py with Playwright (8 passed); tests/test_relations_asof.py and tests/test_remote_items.py; ruff clean. Not run: the unit suite and the other browser files (the factory and the merge queue run them). Local main has no commits past the branch's base, so there was nothing to merge.
