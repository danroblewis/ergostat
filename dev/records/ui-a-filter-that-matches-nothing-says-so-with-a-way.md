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
