# ui-the-record-folds-runs-of-identical-events: The Record folds runs of identical events

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q33 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record

**The problem:** On ticket-factory the Record is mostly 'auxiliary.set team-reviewing teammate {"value":0}' every 5 s, which buries the one-a-minute 'block.commanded fixer'.

**The change:** Consecutive events with the same type, source, item and data become one row with '×N' and the first and last time; clicking it lists them.

**User stories it serves:** C5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/record no two adjacent rows have identical type, source and data text; a row containing '×' followed by a number exists.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. `eventsTable` (ergostat/web/static/details.js) takes a third argument, `fold`; only the Record page
(pages.js, local and remote record) passes it, so an item's own event list is unchanged. A run is consecutive events
with equal type, source, item and data (the shown change); it is one row: the type, then `×N`, the first and last
time as `first–last`; clicking the type lists the run's events in the side panel (the existing detail panel, no new
panel), each opening as one event does. Choices made with nobody to ask (the reversible ones): a run folds only
within the 80 events the page asks for, so a run longer than that shows as `×80` at most; the remote record folds the
same way. Net code: 14 lines (details.js +13, style.css +1, pages.js 0).

Test: tests/test_items_page.py::test_the_record_folds_runs_of_identical_events (the acceptance: no two adjacent rows
equal in type, source and data; a `×6` and a `×3` row; a different value or another event in between starts a new
row; clicking lists all 6). Seen to fail with the fold switched off in pages.js (row assertion) and with the click
opening one event instead of the run (timeout waiting for the list). tests/test_items_page.py (22 passed) and
tests/test_page_refresh.py (8 passed) run with Playwright under the watchdog, rc 0; ruff clean. Not run here: the unit
suite, tests/test_diagram_rendering.py, tests/test_page_polling.py (left to the factory and the merge queue). Main is
already an ancestor of the branch; nothing to merge.
