# ui-requests-that-are-alike-fold-into-one-with-a-cou: Requests that are alike fold into one, with a count and one answer

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q50 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side list; /items 'Modelling requests'

**The problem:** On big 24 'no-unit' requests each take a seven-line row with its own Deny; four fill the list; the one real alarm and everything else are pushed away. /model says 'Changes to review: Nothing waiting' at the same time.

**The change:** Group by (code, asker): one <details> row '24 stocks have no unit (api, billing, build, data, support, web) · Deny all', whose body lists the members, each with its own control. /model's 'Changes to review' counts the same held requests.

**User stories it serves:** E4, E1, H1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/ the side list has one entry containing '24' and 'no unit'; opening it lists 24 members; every other entry in the list is visible without scrolling at 1440x900; /model does not say 'Nothing waiting' while requests are held.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
