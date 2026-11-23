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

Build step, round 1: `build` failed with rc 5 and no test failed. scripts/affected_tests.py picks only
tests/test_items_page.py, the one test file this branch changes; that file needs a browser and the build step runs
without Playwright, so the whole module is skipped ("1 skipped") and pytest exits 5 (no tests collected). Under
Playwright and the watchdog the same file passes: 22 passed, rc 0 (re-run after the failure). No code changed: the
fault is in the build step's choice of tests (a test file only for the browser and no browser), which is outside this
gap (lesson 13) and belongs in a gap of its own, e.g. affected_tests.py leaving out the four browser files, or
`build_browser = true`. Until then this gap needs the four browser files run in the merge queue, which already runs
them in full.

Build step, round 1, second failure (rc 5 again: only the browser file was picked, and it skips without
Playwright). Fixed with a test; no page code changed. tests/test_graph_cli_web.py::test_only_the_record_folds_runs_of_identical_events
reads the served details.js and pages.js without a browser. It checks that the run key is type, source, item and
data, that only the Record's two calls ask for the fold, and that the run list doesn't. It sits in a unit file the
branch now changes, so the build step has tests that run. It checks the source text, not behaviour; the behaviour is
the browser test above. Seen to fail with `e.source` dropped from the key, and with the local Record's fold switched
off. The whole file passes (32 passed); ruff clean.

Round 2: main (9bfce815) merged in. The two conflicts (tests/test_graph_cli_web.py, tests/test_items_page.py) were
both new tests added side by side; both sides were kept, and no page code conflicted. After the merge
tests/test_graph_cli_web.py has 38 passed and ruff is clean. With Playwright under the watchdog,
tests/test_items_page.py has 27 passed and 1 failed; the Record fold test passes. The failure is
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, which comes from main. It fails alone too (rc 1,
timeout in `wait_for_function` for / off/ in `#running` on /items). It covers the header and the project switcher,
which this branch does not touch (the branch changes only `eventsTable`/`showRun` in details.js, the Record's two calls
in pages.js, and one CSS rule). So it is reported, not fixed here (lesson 13). Not confirmed on clean main: making a
worktree of main under /tmp was refused here. Not run: the unit suite, tests/test_diagram_rendering.py,
tests/test_page_polling.py, tests/test_page_refresh.py (left to the factory and the merge queue).

Round 3: main (2a97eafb) merged in. The conflict in tests/test_items_page.py was the branch's fold test and main's
new `add_record`/`record_rows` helpers and crossing test, all in the same place; all three were kept, one after the
other. No page code conflicted, and both Record calls in pages.js still pass `fold`. main's crossing test seeds events
that each have different data, so the fold leaves its rows alone. tests/test_graph_cli_web.py: 41 passed. ruff is
clean. With Playwright under the watchdog, tests/test_items_page.py has 28 passed and 1 failed, rc 1. The fold test
and main's crossing test both pass. The failure is again
test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart, from main. This time it timed out at line 1286
(`wait_for_function` for the other project's `#project` option). That is the header's project switcher, which this
branch does not touch, so it is reported, not fixed (lesson 13). Two commands were refused here: writing the
test-file log to /tmp, and a shell heredoc to append this section (so it was added with the editor instead). Not run:
the unit suite, tests/test_diagram_rendering.py, tests/test_page_polling.py, tests/test_page_refresh.py (left to the
factory and the merge queue).
