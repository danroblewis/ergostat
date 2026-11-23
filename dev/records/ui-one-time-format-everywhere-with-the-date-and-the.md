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

Round 2: the merge of main (9bfce815) conflicted only in `tests/test_items_page.py`, where both sides added a test at
the end of the file. Both are kept: the branch's `test_every_time_is_one_stamp_with_its_date_and_zone` and main's
`test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. No page code changed this round. ruff is clean;
`tests/test_time_stamp.py` passes (3 passed). With Playwright under the watchdog, `tests/test_items_page.py` gave
27 passed and 1 failed (rc 1), twice. The failure is main's new test: at `tests/test_items_page.py:1248` it waits
30 s for the other project's entry in the header's `#project` list. It failed alone too, with the branch's stamp
test passing in the same run. I read it as unrelated to this gap: the branch's only util.js change adds `stamp` and
`timeField` and removes `tidy`, which is unused on main. It touches neither the switcher (`refreshProjects`) nor the
server's lister. My reading of the cause, which I have not run on main: each server makes its project list once at
start-up and then every 60 s (`ergostat/web/server.py`, `LIST_EVERY`). A project started before the other is up can go
60 s without listing it, and the test waits only 30 s. It is left for main, per lesson 13. The command that would have
written this section, a `cat >> … <<'EOF'` followed by `git add` and `git commit`, was refused, so it was written with
the editor.

Round 3: the merge of main (2a97eafb) conflicted only in `ergostat/web/static/details.js`, at a goal's Crossings. Main
made each crossing a link to the Record for that span (`table.crossings`, `/record?about=…&from=…&to=…`), and the
branch had put the time through `stamp`. Both are kept: main's link, with `stamp(e.time)` as its text. Main also added
a "from … to …" line to the Record when it is opened from a crossing, with its own `toLocaleString` format. It is on
/record, a page this gap covers, so its `at` is now `stamp` (pages.js, 0 net lines). Net code is still +11 lines.
ruff is clean; `tests/test_time_stamp.py` passes (3 passed). With Playwright under the watchdog,
`tests/test_items_page.py` gave 28 passed and 1 failed (rc 1), twice. The failure is the same test as in round 2,
main's `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`, now at `tests/test_items_page.py:1325`,
the 30 s wait for the other project in `#project`. The branch's stamp test passed in both runs. As in round 2 it is
left for main (lesson 13). A command that printed the test's lines with `grep`/`sed` was refused, so I read the file
with the editor's reader instead.

Round 4: the merge of main (7cb97857) conflicted only in `tests/test_items_page.py`, where both sides added a test
after `test_a_remote_items_file_field_never_reads_a_local_file`. Both are kept: the branch's
`test_every_time_is_one_stamp_with_its_date_and_zone`, then main's
`test_each_kinds_legend_says_which_states_finish_and_a_one_state_kind_lives_on`, each with its own `finally`. No page
code changed this round, and net code is still +11 lines. ruff is clean, and `tests/test_time_stamp.py` passes
(3 passed). With Playwright under the watchdog, `tests/test_items_page.py` gave 26 passed and 6 failed (rc 1). The
branch's stamp test passed, and it passed again in a later run of its own. The six failures:

- `test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set`,
  `test_the_model_changes_are_found_by_heading_search_and_panel`, `test_a_valves_leased_items_are_listed_live`,
  `test_a_snapshot_lists_a_parts_items_and_opens_its_set` and `test_a_set_left_out_of_a_snapshot_says_so`. Each failed
  again when run alone. Each waits for a stock's or valve's Dynamics panel to fill in (`#detail .item-set`,
  `#detail .leases-line`), and it never does. I found a cause in main's code, not the branch's, though I have not run
  it on main. Main's `openNodeSD` (`ergostat/web/static/dynamics.js`, merged with
  `factory/ui-everything-clickable-in-the-diagram-can-be-reach` / `ui-what-i-selected-stays-selected…`) first shows a
  placeholder `wait`. Then it calls `panelLoading`, which redraws the panel through `showDetail` and so removes `wait`
  from the page. After the part's answer comes, `if (!wait.isConnected) return;` is always true, so the panel stays at
  "Loading…". The branch does not touch dynamics.js, `panelLoading`, `showDetail` or itemsets.js. It is left for main
  (lesson 13).
- `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`: the same 30 s wait for the other project in
  `#project` as in rounds 2 and 3. It is left for main.

Refused this round, as given: the whole-file browser run piped into `> /tmp/items.log … grep`, then re-run without
the pipe. A probe script at `/tmp/probe/probe.py` (the file tools are confined to /work) and
`uv run --with playwright==1.63.0 python /tmp/probe/probe.py`, to print the panel's page errors. And
`git diff $(git merge-base HEAD^1 HEAD^2) HEAD^2 -- …`, re-run with the two commits named.
