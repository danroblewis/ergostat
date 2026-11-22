# ui-one-time-format-everywhere-with-the-date-and-the: One time format everywhere, with the date and the zone

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q34 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record, loop panel crossings, /items, /item/…, request pages

**The problem:** Four formats, one with a zone: '04:04:36' (Record), '11/22/2026, 03:27:22' (item), 'Nov 22, 03:55' (list), '2026-11-22T11:22:55Z' (a field, 8 h away). Fields print epoch seconds as '1,795,346,621'; event data rounds them to 6 digits ('1795350000').

**The change:** One formatter: '2026-11-22 04:03:55 PST' (the zone's short name; the date dropped only inside a table whose caption gives it). Format every *_at, raised, since and started field with it. Print event data unrounded.

**User stories it serves:** C5, F2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On /record, /item/ticket%2FSCRUM-2 and a goal's Crossings every time matches /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+/ or sits in a table whose caption carries the date and zone; no cell matches /1,7\d\d,\d{3},\d{3}/; 'done_at' in Events equals the field's value.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. +11 net lines of code under `ergostat/web/static/` (util.js +12, details.js 0, pages.js −1), within the 60.

- `stamp(t)` in util.js gives `2026-11-22 04:03:55 PST`: the browser's zone, by the short name `Intl` gives it
  (`PST`, or `GMT+1` where a zone has none). It is used on the Record (the "when" column and the event's panel), a goal's
  Crossings, an item's page (moves, field history, lease history, refused), and the Items page ("moved", "done by" and its
  p90). Request pages are item pages, so they get it too.
- `timeField(name, v)`: a field named `*_at`, `at`, `raised`, `since` or `started` that holds epoch seconds or ISO text
  (`2026-…T…`) is shown as a stamp. This covers the item page, the Items list, a remote item's fields, sub-records and
  each field's history. Values outside 1973–5138 are left as they are, so a small count named `since` still reads as a
  number.
- Event data on the Record and in Events is printed unrounded. `tidy`, its only user gone, is removed. DESIGN.md
  "Numbers" says so, and a new "Times" line names the formatter.
- Choice made alone (the most reversible one): the full stamp is used everywhere and no table drops the date under a
  caption. The definition allows that but does not require it, and the full stamp meets the acceptance check with no
  caption code.
- Left as they were, since they are not on the gap's pages: the times in the side panel's sensor readings, valve openings
  and item sets; the charts' axes; the timeline; the snapshot banner; and the relative times ("3m ago", "for 2h").

Tests: `tests/test_items_page.py::test_every_time_is_one_stamp_with_its_date_and_zone` (the acceptance check, with the
browser in America/Los_Angeles, so the stamps must end in PST/PDT). I broke each guarded piece once, and the test failed
each time: Crossings back on toLocaleTimeString (`['04:51:03', '04:49:43']`); the Record's "when" column the same; the
data cell rounded to 6 digits (`[1795350000] == [1795351894.4567]`); the fields without `timeField`
(`['1,795,351,904', '2026-11-22T12:45:03Z', …]`). With Playwright under the watchdog, `tests/test_items_page.py` passed
(22 passed, rc 0, none skipped). `tests/test_page_refresh.py` failed 2 of 4 whole-file runs on
`test_other_pages_left_open_change_nothing`: unexpected SVG `g` and `hidden`-attribute mutations on /loops, /agents or the
process map. None of those pages calls stamp, timeField or dataCell. The test passed in the other 2 whole-file runs and in
2 runs of its own (3 passed each), so it is intermittent. The command I gave to check it on clean main,
`git worktree add --detach /tmp/main-wt main`, was refused, so this has not been shown on main.

`tests/test_diagram_rendering.py`, whole file, serially under the watchdog: 196 passed and 4 failed (rc 1) in 47 min.
Three of the failing tests also failed on a rerun alone, each on a fixed time bound:
`test_every_view_draws_cleanly_and_in_time[coordinator]` (routing open=* took 40218 ms, bound 20000),
`[image-squeeze]` (38406 ms, bound 20000), and `test_a_big_tangled_model_lays_out_in_time_and_cleanly` (a draw took
3568 ms, bound 2500). The fourth failure's name was cut from the filtered output and has not been found. These tests time
diagram layout and line routing (layouts.js, avoid.js, the libavoid worker), which this change does not touch: util.js
only gains stamp and timeField and loses tidy. I read them as this container being too slow for those bounds, not as this
change. That is not proven: the command I gave to run them on main's page code,
`git checkout main -- ergostat/web/static/util.js ergostat/web/static/details.js ergostat/web/static/pages.js`, was refused.
The merge queue's run on its own machine will settle it. ruff is clean. main has nothing the branch lacks
(`git rev-list --count HEAD..main` is 0).

Round 1, after the build step: the build step (`affected_tests.py`) ran only `tests/test_items_page.py`, which skipped
because it has no Playwright, so pytest exited with rc 5 (nothing ran). No page code changed. A new unit test file,
`tests/test_time_stamp.py`, reads util.js, details.js and pages.js with no browser and checks three things. There is
one `stamp` that gives date, time and short zone. Its `TIME_FIELD` rule matches `*_at`, `at`, `raised`, `since` and
`started`, and not `started_by` or `status`. The Events table and the event panel use `stamp`, `dataCell` no longer
rounds, and these pages call no `toLocaleString`. It passes (3 passed) and ruff is clean. Not seen: a script that
copied the static files to /tmp, broke each guarded piece and ran these tests against the copy
(`uv run python /tmp/mut/run.py`) was refused. So these new tests have not been seen to fail. The browser test was
seen to fail on each break earlier in round 1.
