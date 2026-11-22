# ui-from-a-crossing-to-the-record-narrowed-to-that-g: From a crossing to the Record, narrowed to that goal and time

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q31 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** goal evidence panel; /record

**The problem:** Crossings and Decisions rows are not clickable; the Record filters by event type only, so a goal or agent name answers 'Nothing recorded yet.'; the filter is not in the address.

**The change:** Each crossing row links to /record?about=<goal>&from=…&to=…, which shows events of the goal, its controller, its actor and its valve. The filter box also matches item and source. The filter and the window live in the address.

**User stories it serves:** C5, H6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797 clicking a crossing of billing-q0-low lands on /record with 'about=' in the URL and only rows whose type, item or source belong to that goal; typing 'fixer' on :8791/record shows rows; reloading the URL keeps the filter.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built (about 34 net lines outside tests). Choices made without anyone to ask, each the smaller, reversible one:

- A crossing's link is `/record?about=<goal>&from=<its time>&to=<the next crossing's time, else the window's end>`
  (`ergostat/web/static/details.js`). Only crossing rows link; Decisions rows do not (The change names crossings only).
- "The goal, its controller, its actor and its valve": the server (`_record_rows` in `ergostat/web/server.py`) takes the
  goal's name, its loop's valves and the agents filling its controller and valves, and returns events whose item is
  one of those names or whose source is one of them (or `<name>/<instance>`). Sensors are left out. A name that is not
  a goal narrows to that one name, never to everything. The store is unchanged: these are several exact queries
  (item, source) merged by `seq`, each capped at the page's 80.
- The filter box sends `match=`: an event's type (as before: exact, `prefix*`, commas), or its item or source equal to
  the text (exact, not a substring). `?type=` in old links still fills the box. With `about=` too, the goal's events
  are narrowed by the same test.
- The filter, Show runs, about/from/to and the earlier scope parameters go back into the address with `replaceRoute`
  (no new history entry), so a reload keeps them.
- The acceptance names demos on :8797 and :8791, which are not running in this container. The test
  (`tests/test_items_page.py::test_a_crossing_opens_the_record_narrowed_to_its_goal_and_time_and_the_filter_stays_in_the_address`)
  runs on image-squeeze (the :8791 demo) instead: a seeded crossing of `ideas-ready` stands in for billing-q0-low, and a
  seeded event from source `fixer` stands in for :8791's fixer.

Breaks seen to fail the test (lesson-9), each reverted: the window `from`/`to` ignored (a later event shown); `about`
ignored (another item's event shown); the address not written (no `match=fixer` in the URL); the filter matching
type only (the fixer row never shown).

Tests run: tests/test_items_page.py (22 passed, rc 0, Playwright, no skips); test_page_refresh.py's two Record tests
and test_diagram_rendering.py::test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back (3 passed);
tests/test_page_polling.py alone (17 passed, rc 0); tests/test_graph_cli_web.py alone (31 passed); ruff clean. A first
run of test_page_polling.py with test_graph_cli_web.py together had 1 failure that the output kept did not name; a
second combined run printed no FAILED line, and each file passes alone. Not run: the whole unit suite,
test_diagram_rendering.py in full, demo_check (no example touched), and a merge of main (main is the clone's base,
unchanged since).

Round 1, after the build step: `build` failed with rc 5, not on a test. Its affected-tests selection named only
tests/test_items_page.py, which skips as a whole without Playwright, so pytest collected nothing. No page code changed.
Added `tests/test_graph_cli_web.py::test_the_record_narrows_to_a_goal_and_its_window_and_the_filter_matches_item_and_source`,
a test that needs no browser, of the server's narrowing (`about=` with the goal's controller, valve and agents; `from`/`to`;
`match=` as type, item or source; an unknown goal gives nothing). The build step now selects that file too. The test
failed when the controller's, valves' and agents' names were dropped from `_record_rows` (reverted). Run:
tests/test_graph_cli_web.py (32 passed); ruff clean.

Round 2, answering the review's one finding (blocking): with both `about=` and `match=`, each question was capped at
the newest n before the match was applied, so older matching events were dropped. Now `_record_rows`
(`ergostat/web/server.py`) puts the match into each question itself, for each of the goal's names: item=NAME or
machine=NAME, each with type=MATCH, or with the other field equal to MATCH (plus item=MATCH and machine=MATCH when
MATCH is one of the goal's names). So the cap of n applies only after the match, and the merged newest n is exact.
The filter after the queries is gone. With `about=`, a type in `match=` now also takes commas, as it already did
without `about=`. New test:
`tests/test_graph_cli_web.py::test_the_goals_filtered_rows_are_not_lost_behind_more_than_n_newer_events_of_one_name`
(n=3, with five newer non-matching events of the goal and five of its agent `cleaner`; matched by type, by item and
by the goal's own name). It fails on the round-1 code (`[] == ['loop.off']`) and when the match is dropped from the
questions. Both breaks were reverted.

Also found in this round: the first full run of tests/test_items_page.py failed once, at line 422 of this gap's own
browser test. The test passed when run alone. The fault was in the test, not the page: the unfiltered Record already
holds `mk-fixer-source`, so waiting for that text could pass before the filtered rows were drawn, and the test then
read the unfiltered rows. The test now waits until all drawn rows are fixer rows. Only the test changed.

Tests run: tests/test_graph_cli_web.py (34 passed); tests/test_items_page.py with Playwright under suite_watch, twice
after the test fix (22 passed each time, rc 0, no skips); ruff clean. Not run: the whole unit suite, the other
browser files, demo_check (no example touched). No merge of main was needed: `git log HEAD..main` is empty.
