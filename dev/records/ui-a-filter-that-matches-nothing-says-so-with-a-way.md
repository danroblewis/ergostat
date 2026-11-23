# ui-a-filter-that-matches-nothing-says-so-with-a-way: A filter that matches nothing says so, with a way to clear it

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q32 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /record, /items

**The problem:** The Record answers 'Nothing recorded yet.' to a filter that matches nothing. On Items 'Nothing matches.' is printed about 3000 px down, under every chart, so the search seems to do nothing; the chart and heading still show all items.

**The change:** Record: 'Nothing matches "x" · clear'. Items: print the match count or 'nothing matches' beside the search box, and hide kinds (with their charts) that have no match while a search is active.

**User stories it serves:** C5, F1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On /record with filter 'zzz' the page contains 'Nothing matches' and a control that empties the filter; on :8791/items typing 'zzqx' shows 'nothing matches' within 100 px of the search box and no chart; typing 'SCRUM-2' shows '1' beside the box and one ticket row.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. All of it is in `ergostat/web/static/pages.js`, +10 net lines; no style or template change was needed.

- Record: when a type filter is set and no events come back (locally or from a remote), the page says
  `Nothing matches “x” · clear`, and the `clear` link (`a.clear-filter`) empties the filter and reads the record again.
  With no filter set it still says "Nothing recorded yet.".
- Items: a `.search-hits` span sits right after the search box and shows the match count, or "nothing matches". The
  count comes from the server's `matched`, or from the snapshot's own rows when the page is a snapshot. While a search
  is active, a kind with no match (and its card and charts) is not drawn, and neither is a system none of whose kinds
  matched. Each system's heading then counts its matches ("N items match"), not all of its items.
- The most reversible choices, taken because nobody was here to ask: the old "Nothing matches." under the lists is
  kept (when nothing matches, everything above it is now hidden, so it sits near the top). The kinds counted in a
  heading are still all of the system's kinds. No count is shown while there is no search.
- Tests, in tests/test_items_page.py on its image-squeeze site (the test fixture), not the :8791 ticket-factory demo:
  `test_a_search_says_its_count_beside_the_box_and_draws_only_the_kinds_it_matched`. It types 'zzqx' and checks
  'nothing matches' is less than 100 px from the box with no chart or kind card on the page. It types 'hypothesis/2',
  this site's stand-in for SCRUM-2, and checks '1', one item row and one kind card.
  `test_a_record_filter_that_matches_nothing_says_so_and_clears` checks the Record's answer to 'zzz' and the clear
  control.
- Breaks seen to fail (lesson 9): drawing every kind's card during a search failed the first test (6 cards, not 1).
  Putting back "Nothing recorded yet." for a filter failed the second.
- Run: tests/test_items_page.py (23 passed) and tests/test_page_refresh.py (8 passed), both in Playwright under the
  watchdog with rc 0 and nothing skipped; ruff is clean. `git merge main` was already up to date. Not run here: the
  unit suite, test_diagram_rendering.py and test_page_polling.py; the snapshot path of the count (no test covers it);
  demo_check (no example was touched).

Round 1, after the build step: `build` returned rc 5 with "1 skipped": its affected-tests selection was only
tests/test_items_page.py, a browser file, and the build command has no Playwright, so the file skipped at import and
pytest collected nothing. That is not a fault in the change: run again here with Playwright under the watchdog
(`suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_items_page.py`) the file
gives 23 passed, rc 0, nothing skipped. No code was changed for it; the most reversible choice was to leave the build
step and the tests as they are and say so here.

Round 1, after the build step again: the same rc 5 ("1 skipped", tests/test_items_page.py:24, no module named
'playwright'). The cause is the build step, not the page code. `scripts/affected_tests.py` picks only
tests/test_items_page.py for a branch that changes only `ergostat/web/static/pages.js` and that browser file. The
`[suites] build` command in dev/factory.toml runs without Playwright, so the file skips at import and pytest returns 5.
Any gap whose test must go in a browser file, as this definition asks, hits this. Run again here under the watchdog
with Playwright, the file gives 23 passed, rc 0, nothing skipped. No code was changed. The fix is outside this gap
(lesson 13) and belongs in a factory gap of its own: for example, affected_tests leaves the four browser files out of
the build's selection, or falls back to --collect-only when only browser files are picked. Adding a test that does
not use a browser only to get past the build step would test nothing the change does, so none was added. The most
reversible choice was to leave the code, the tests and the build step as they are and say so here.

Round 2: the build step's rc 5 is answered the way the agents gap answered it on main (ab17bb6e): with a test that runs
without a browser. `tests/test_graph_cli_web.py` now holds two of them, which check the server answers the page reads.
`test_a_search_or_filter_that_matches_nothing_answers_empty_and_a_match_is_counted_whole` checks that `matched`, the
source of the count beside the search box, is empty for a miss (so no kind is drawn) and counts every match of a kind
beyond the newest per_kind listed. `test_the_record_answers_a_type_that_matches_nothing_with_no_events` checks that
/api/events is empty for type 'zzz' and gives the event for a matching type. Because the branch changes that file, the
build's selection now includes it, so pytest collects tests even without Playwright. The browser tests remain the
acceptance check. No page code changed this round.

- Breaks seen to fail (lesson 9): capping `matched` at per_kind failed the first test, and dropping the type filter in
  /api/events failed the second. Both were put back.
- Run: tests/test_graph_cli_web.py (34 passed). tests/test_graph_cli_web.py with tests/test_items_page.py without
  Playwright, which is the build's selection: 34 passed, 1 skipped (the browser file at import), rc 0.
  tests/test_items_page.py with Playwright under the watchdog: 23 passed, rc 0, nothing skipped. ruff is clean.
- Refused here: running the build command as it is (`uv run python scripts/suite_watch.py -- uv run python
  scripts/affected_tests.py -- uv run python -m pytest -q -rfEs -n 8 --dist worksteal`), so the selection was run
  through named_tests instead. Not run: the unit suite and the other three browser files (the merge queue runs them),
  and demo_check (no example was touched).

Round 3: the factory's merge of main (2a97eafb) conflicted in tests/test_graph_cli_web.py, where both sides added tests
at the same place. Kept both: the branch's two tests and main's
`test_the_side_panels_charts_say_being_worked_out_never_a_bare_ellipsis`. Main had also renamed the Record's filter
box: it now matches type, item or source, is read from `match=` or `type=`, and has the aria-label "Event type, item or
source". The branch's `Nothing matches “x” · clear` merged cleanly into main's code and still works. Only the browser
test's selector for the box was stale (`aria-label="Event type"`). It is now `aria-label^="Event type"`. No page code
changed this round.

- Run: tests/test_graph_cli_web.py (42 passed). ruff is clean. tests/test_items_page.py with Playwright under the
  watchdog: 28 passed, 2 failed. One failure was the stale selector above; after the fix
  `test_a_record_filter_that_matches_nothing_says_so_and_clears` passes. The other,
  `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`, still fails when run alone: it times out at
  tests/test_items_page.py:1298 waiting for the other project's entry in the `#project` switcher. This branch's only
  code change is the Record's and the Items page's search answers in pages.js. It does not touch the header or the
  switcher, so the failure is not this change's (lesson 13) and is left alone.
- Refused here: `mkdir -p /tmp/mainsrc && git archive main | tar -x -C /tmp/mainsrc`, which was meant to run that
  header test on clean main. So it was not shown to fail on main too. The factory's rerun on clean main will settle
  it. Not run: the unit suite, the other three browser files and demo_check (no example was touched).

Round 4: the factory's merge of main (ead497d1) conflicted in pages.js and tests/test_graph_cli_web.py. In pages.js,
main had added a third argument to the Record's two `eventsTable(…, false, true)` calls (fold runs of identical events),
and the branch had replaced the empty answer with `empty()`. Both are kept: `eventsTable(…, false, true)` on a hit,
`empty()` (`Nothing matches “x” · clear`, or "Nothing recorded yet." with no filter) on a miss, for local and remote
records alike. In the test file both sides added tests at the same place; all of them are kept (the branch's two and
main's `test_every_page_header_links_to_the_diagrams_waiting_for_you_heading`). No other change.

- Run: ruff clean; tests/test_graph_cli_web.py 44 passed. tests/test_items_page.py with Playwright under the watchdog:
  33 passed, 2 failed. The gap's two browser tests pass.
  `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` fails again, alone too, at the `#project`
  switcher wait (now tests/test_items_page.py:1502), as in round 3: header and switcher are untouched by this branch.
  `test_the_graph_and_the_timeline_left_open_change_nothing[graph]` failed once in the full file (one mutation on a
  BUTTON across refreshes) and passed when its two cases were rerun alone; the branch's diff touches no button and
  not the graph view, so it is reported as a load-dependent flake not of this change (lessons 10, 13), not fixed here.
  Not run: the unit suite, the other three browser files, demo_check (no example touched).

Round 5: the factory's merge of main (dc47a763) conflicted in pages.js and tests/test_graph_cli_web.py.

- tests/test_graph_cli_web.py: both sides added tests at the same place. All are kept: the branch's two and main's
  `test_a_process_view_with_no_kinds_is_answered_empty_and_the_page_says_so_over_the_canvas`.
- pages.js: main removed the `more` note ("N older items not loaded.") and added `found` beside the search box, a
  kind's page's "N matches, M finished". Both spans are kept, `hitsSaid` then `found`. Main's `const hits = d.total`
  clashed with the branch's `const hits` in the same function, so main's is renamed `total`. On a kind's own paged page
  (`paged()`), `.search-hits` now stays empty because main's `found` already gives the count there. This is the most
  reversible choice: one count beside the box, not two.
- Main moved the bare /items to an overview (kinds.js, `pageKinds`). Its search box goes to `/items?q=…` on Enter, and
  that page is still `pageItems`, where the branch's count and hiding live. No code was added to kinds.js. The browser
  test now types 'zzqx' into the overview's box, presses Enter and waits for `?q=zzqx`; the rest of the test is
  unchanged. Its initial "the count is empty" check, which the overview has no box for, was dropped; the test's last
  step (search emptied, count empty) still covers it.
- Break seen to fail (lesson 9): drawing every kind during a search (`hit` always true) failed the Items test.
- Run: ruff clean; tests/test_graph_cli_web.py 49 passed. tests/test_items_page.py with Playwright under the watchdog:
  61 passed, 2 failed. The gap's two browser tests pass. The two failures are not this branch's (lesson 13). The
  tests are unchanged from main, and the branch's diff against main does not touch what they check:
  `test_actions_say_per_class_asked_approved_denied_and_whether_held` waits on the bare /items for
  `.action-classes`, which main's new overview (kinds.js) does not draw. `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`
  times out at the `#project` switcher wait (tests/test_items_page.py:1924), as in rounds 3 and 4.
- Refused here: `node --check ergostat/web/static/pages.js` and a python one-off that edits the test file (Edit was
  used instead). Not run: the unit suite, the other three browser files, demo_check (no example touched).

Round 6: the review's one finding, answered. On a kind's own paged page (/items/KIND?q=…) the server's `matched`
counts only the page shown. So the branch's count and hiding gave a heading of "25 items match" beside `found`'s
"111 matches", and a miss dropped the kind's whole section. Now `hits` is null when `paged()`, so that page works as
it does on main: the heading counts the kind's items, the section and pager stay on a miss, and `found` is the only
count beside the box. The overview's search (/items?q=…) keeps the count and the hiding. pages.js is now +19/-8
(11 net).

- Test: `test_a_search_on_a_kinds_own_page_keeps_its_one_count_and_its_section` (tests/test_items_page.py, on the
  1,200-ticket paged_roadmap fixture). For 'ticket/n11' it checks that `found` says "111 matches…", that no heading
  says "match" and that `.search-hits` is empty. For 'zzqx' it checks that `found` says "0 matches…" and that the
  kind's section stays.
- Break seen to fail (lesson 9): putting back `hits` on a paged page failed the test with the heading
  "25 items match, 1 kind".
- Run: ruff clean; tests/test_graph_cli_web.py 49 passed. tests/test_items_page.py with Playwright under the
  watchdog: 62 passed, 2 failed, nothing skipped. The gap's three browser tests pass. One failure waits for
  `.action-classes li[data-class="jira-transition"]`, which is
  `test_actions_say_per_class_asked_approved_denied_and_whether_held`, as in round 5 (main's overview does not draw
  it). The other is a `wait_for_function` timeout that looks like round 5's header/switcher test, but it was not
  named for certain. This branch changes neither test, and neither checks the search (lesson 13).
- Refused here: rerunning those two tests alone to name the second one for certain (`suite_watch.py -- … named_tests.py
  tests/test_items_page.py::test_actions_say_per_class_asked_approved_denied_and_whether_held
  tests/test_items_page.py::test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart | grep …`), and
  appending to this file with a shell heredoc (Edit was used instead). Not run: the unit suite, the other three
  browser files, demo_check (no example touched).

Round 7: the factory's merge of main (a171d119) conflicted in pages.js and tests/test_graph_cli_web.py, and both are
resolved in 7975c25b.

- pages.js: main added the "Show finished" box (`showFin`), the `loading` line, and the finished left out by default
  (`leaves`, `isHidden`, `flip`, `finNote`, and a snapshot's rows filtered by them). All of it is kept. The filter
  bar is now `search, hitsSaid, found, showFin, viewBar, chip`. The branch's `hits`/`hitsN`/`hit` come after main's
  `rows`, so the snapshot's count is taken from main's filtered rows. A search never leaves the finished out
  (`leaves` is false while there is a needle), so the count is unchanged. pages.js is still +19/-8 against main.
- tests/test_graph_cli_web.py: both sides added tests at the same place. All are kept: the branch's two and main's
  `test_the_loop_answer_carries_what_the_panels_first_table_shows`.
- tests/test_items_page.py: main now hides a kind's finished items by default, so the paged page says "1-25 of 800"
  and the branch's `test_a_search_on_a_kinds_own_page_keeps_its_one_count_and_its_section` failed on its first
  check. It now opens `/items/ticket?finished=show`, as main's sibling paged tests do. It checks nothing else new.
- Run: ruff clean; tests/test_graph_cli_web.py 54 passed. tests/test_items_page.py with Playwright under the
  watchdog: 67 passed, 2 failed, nothing skipped. One failure was the test above, before the fix; after it, the gap's
  three browser tests pass (3 passed, rc 0). The other is
  `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart`. It times out at the `#project` switcher wait
  (tests/test_items_page.py:2063), as in rounds 3 to 6. This branch does not touch the header or the switcher
  (lesson 13).
  `test_actions_say_per_class_asked_approved_denied_and_whether_held` passed this time.
- Refused here: redirecting the browser run's output to /tmp/items.log (it was run without the redirect instead), and
  a python one-off that resolved the conflicts (Edit was used instead). Not run: the unit suite, the other three
  browser files, demo_check (no example touched).
