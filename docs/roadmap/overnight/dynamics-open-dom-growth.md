# dynamics-open-dom-growth: find out whether the Dynamics page with all systems open leaks DOM nodes, and fix what is true

depends-on: []

`tests/test_page_polling.py` failed in 3 of 30 merge-queue browser runs in the last 6 hours (2026-11-21) with `DOM nodes grew by 2717`, `1334` and `779`, on `diagram?view=dynamics&open=*`, and passed on retest. One run read nodes 3869 to 6586 and listeners 1153 to 2069 while the page refreshed. It happens under machine load, but it may be a real leak that load only makes visible, and the owner has named UI problems on large systems as something to fix before release. Do not quarantine this test and do not loosen its bound to make it pass.

## Definition of done
1. Measure it: on `diagram?view=dynamics&open=*` with a large model, record DOM nodes and listeners over at least 30 refreshes, once at normal speed and once with refreshes delayed or overlapping (CPU throttled through CDP). Say in the definition's *Where it stopped* what you measured.
2. If nodes or listeners keep growing with refreshes, or a slow refresh overlaps the next and leaves its nodes behind: fix that in the page code, so both stay bounded in both runs.
3. If nothing grows once the page has settled, and the failure is the test reading mid-render: make the test wait for the render in progress to finish before it reads, keeping the same bound.
4. A test holds the result under CPU throttling, so it does not depend on how busy the machine is.

## Files to touch
`ergostat/web/static/` (the diagram refresh code, if it leaks), `tests/test_page_polling.py`.

## Risks
- lesson-3: an unreadable metric fails the test, it never passes it.
- Do not change the refresh rate to hide the growth.

## Acceptance tests
- `tests/test_page_polling.py::test_dynamics_open_stays_bounded_over_30_refreshes`
- `tests/test_page_polling.py::test_dynamics_open_stays_bounded_when_refreshes_overlap`

## Size budget
80 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, 2026-11-21. **Not measured: item 1 is not done, and nothing here has run in a browser.** This container has
no Playwright in the project environment, and the command that adds it (`uv run --with playwright==1.63.0 python -m
pytest ...`) was refused, so `tests/test_page_polling.py` skips here as a whole. Every number this definition asks for
is still to be taken, by the factory's browser run or the next round.

What reading the code found (a reading, not a measurement):
- One refresh of the Dynamics view builds the whole drawing aside and swaps it in with one synchronous
  `svg.replaceChildren(vp)` (`ergostat/web/static/diagram.js` `drawGraph`). Refreshes come from `poll()`
  (`util.js`), which never runs two at once. The router's redraw (`avoid.js` `avoidStart` → `S.redraw`) is also
  synchronous and only runs for the layout now shown. No global keeps an old drawing's elements (only
  `S.sideChartsEl` and `S.legendEl` hold elements, one each, kept on purpose). Listeners are put on the new elements
  and go away with them.
- So an old drawing can only be counted while it is not yet collected. That happens when a refresh's draw slips in
  between the test's look and its read. The failures fit this: the growths (2717, 1334, 779) are not multiples of
  one drawing, and they passed on retest. A pile-up would grow by whole drawings, every run.

What was built, on that reading (item 3, the most reversible choice: tests only, no page code, the bound unchanged):
- `idle_metrics`: a read taken only between refreshes. No poll is running and no lines are being routed before the
  collection, and `S.drawN` is the same before and after it. If a drawing slipped in, the read is taken again. With no
  such read before the deadline, the test fails (lesson-3).
- `quiet_metrics`: two such reads with the same nodes and listeners. Past `SETTLE_S` it returns the last read,
  however high, so growth that never stops still meets the same bound. `settle` and the end read of
  `test_a_page_left_open_does_not_grow` now use these reads.
- `test_dynamics_open_stays_bounded_over_30_refreshes` and `..._when_refreshes_overlap` run on
  `scripts/scale_model.py 20` (`POLL_SCALE_N`). They read nodes and listeners every 5 of 30 refreshes, and each read
  must stay within the existing bound. The second throttles the CPU 4x through CDP once the page has settled, and
  starts three whole relayouts (`S.relayout()`) while the poll's own refresh is on its way, so two refreshes overlap.

Left:
1. Run both acceptance tests and the old parametrized test in a browser. Write the printed series here (item 1).
2. If either grows, the reading above is wrong and the leak is in the page: fix it there (item 2). The tests stay.
3. Lesson-9 not done: break the code and watch the tests fail. For example, keep each old `vp` in a global array in
   `drawGraph`; both new tests should then fail.
4. The unit suite and the four browser files were not run here. Only ruff ran.

After the factory's unit suite failed (its tail showed no failing test): the unit suite run here under
`suite_watch` (`-n 8 --dist worksteal`) gave 2 failed, 2523 passed, 69 skipped, rc 1:
`tests/test_runner_and_state.py::test_a_run_past_its_timeout_is_stopped_with_what_it_started` (FileNotFoundError:
`lsof` is not installed in this container) and `tests/test_daemons.py::test_a_short_lived_daemon_is_sampled_before_it_ends`
(not sampled within 3 s under load). Both pass alone (2 passed). This branch changes neither file nor any code they
run (only `tests/test_page_polling.py`, which the unit suite skips without Playwright), so they are reported as
unrelated (lesson-13), not fixed here.

After the factory's second unit failure: its tail ends at 78% with no failed test and no summary line, so the run
was cut off (watchdog or timeout), not failed by a test. This branch still changes only `tests/test_page_polling.py`.
The unit suite (`dev/factory.toml` `[suites] unit`) runs without Playwright, and that file's module-level
`pytest.importorskip("playwright.sync_api")` (line 25) skips it at collection, so none of its code runs in that
suite. No page code was changed for this. In this round every Bash command was refused (the first one:
`git log --stat -4 | head -60 && ...`), so nothing was rerun and this note is not committed. Left: rerun the unit
suite under `suite_watch` on this branch and on main, find what cut it off, and commit this note.

Round 2, 2026-11-21. Again the shell refused the first command (`git log --stat -5 | head -60 && git diff main
--stat && uv run python -c "import playwright; ..."`). No other route was tried. So nothing was run, measured or
committed this round, and this note is in the working tree only. The note above seems to have been committed since
(f67c7afd, "work the session left uncommitted"), but this round could not check that. By reading only: every
page name the tests use exists in the page code: `S.drawN` (`diagram.js:645`), `S.relayout` (`diagram.js:1252`),
`S.timer = poll(...)` with `.running` (`diagram.js:1256`, `util.js:404`), `S.layout.routing` (`avoid.js:652`) and
`POLLS` (`util.js:401`). No code was changed. Item 1 (the measurement), lesson-9 (break `drawGraph`, watch both
tests fail) and the suite runs are still left, as listed in round 1. They need a round where the shell works and
Playwright with Chromium is there.

After the factory's third unit failure (round 2): its tail reads `1 skipped in 0.68s` and suite_watch `"rc": 5`. That is
pytest's exit 5, *no tests collected*, not a failing test: the run collected one module, and it skipped at collection.
The one module this branch changes, `tests/test_page_polling.py`, skips at collection without Playwright (its
`pytest.importorskip` on line 25). In this worktree the `[suites] unit` command of `dev/factory.toml`
(`pytest -q -n 8 --dist worksteal`, `testpaths = ["tests"]`) collects 2595 tests (`pytest --collect-only -q`, run
here). So the factory's run must have picked the tests from the branch's diff, and that left only this file. The
worktree has no such selection: `affected` is not found under `dev/`. The factory follows its own copy of
`dev/factory.toml` on main, but this round could not read main (`git log --oneline -3 origin/main; git show
origin/main:dev/factory.toml | ...` was refused, and so was `git fetch -q`), so this is not confirmed. No code was
changed for it. The only fix inside this branch would be to skip each test on its own instead of the whole module, so
that something is collected. That would make a unit run with no Playwright "pass" a browser file it never ran
(lesson-3), so it was not done (most reversible: no change). Left: the factory should treat rc 5 from a test selection
of browser files only as "nothing to run" (its own gap), or run this branch's unit suite whole. Then items 1, 3 and 4
of round 1's list are still left, unchanged.

After the same failure came back with the instruction to fix the code: the per-test skip is now done. The file imports
Playwright in a `try` and skips every test with a module `pytestmark` when it is missing. On reflection this is no
wider than before: the module skip was already a skip ("1 skipped"), and now it is 19 skips, each reported with its
reason. It is not a pass, and the browser suite, which runs with Playwright, runs every test as before. The run that
failed (`suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal tests/test_page_polling.py`) now gives
19 skipped, rc 0. No bound, test body or page code changed. Items 1, 3 and 4 of round 1's list are still left: this
container still has no Playwright, so nothing here has run in a browser.

## Where it stopped

Parked by the factory (review/dynamics-open-dom-growth-1, 2026-11-21 15:46).

Done: the test-side changes (idle_metrics and quiet_metrics reads, settle and the old test's end read using them, and the two acceptance tests on scale_model.py 20, one with 4x CDP throttling and three overlapping relayouts). The bound is unchanged and no page code changed. By reading, every page name used exists, and the browser suite runs these tests (slow is not deselected). Left: the measurement of definition item 1, the lesson-9 run with a planted leak, and, depending on what the measurement shows, keeping item 3 or fixing the page under item 2. In every round so far the implementor's shell has been refused or has had no Playwright, so another fix round cannot make progress.

Continued, round 1, 2026-11-22. The shell refused the first command again (`git log --oneline -8 && git status
--short && uv run python -c "import playwright; print('pw ok')"; ls ~/.cache/ms-playwright`). No other route was
tried. So nothing was run, measured or committed in this round, and this note is in the working tree only. No code
changed.

What reading found this round, on the park review's first finding (forced collection undercuts item 3's reading):
the finding holds. `metrics()` calls `HeapProfiler.collectGarbage` before every read, and `drawGraph`
(`diagram.js:644-839`) builds and swaps its drawing in one synchronous task. So a CDP read cannot land in the middle
of a draw, and an old drawing that nothing references cannot be counted after the collection. "An old drawing not yet
collected" therefore does not explain the merge-queue growths. They are either a real reference that keeps old
elements alive (item 2), or nodes outside the drawing that the earlier reading did not check. Where to look first,
from reading only:
- The Dynamics side panel (`charts.js:502-517` `sideCharts`). It is rebuilt every 15 s, or whenever its `sig`
  changes, with new `causesStrip` strips. These strips and their async loads were not traced. If any global, timer or
  late callback holds an old strip, that strip's whole detached subtree stays alive.
- Any closure kept past a draw that holds one element of an old `vp`. Holding one element keeps the whole tree.
  `S.hullDrag`, `S.edgeById` and `S.sdSigns` hold data only, by reading.

So the item-3 test changes are not yet justified as the fix: they make reads wait for idle, and if the leak is real
they may only hide it. They should stay as the reads, though, because the bound is unchanged and growth that never
stops still fails them. Left, unchanged, in this order: (1) run both acceptance tests and the old parametrized test in
a browser (`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py
tests/test_page_polling.py`) and write the printed series here; (2) if the nodes grow, take a heap snapshot's detached
nodes (CDP `HeapProfiler.takeHeapSnapshot`) to find what holds them, and fix that in the page (item 2); (3) the
lesson-9 run with a planted leak (each old `vp` kept in a global array in `drawGraph`); (4) answer the review's other
findings: source the listener bound from the measurement. (The `idle_metrics` docstring is narrowed in this round
to what is checked: no poll running and no routing, with a draw from `S.relayout()` caught only through `S.drawN`.
That is wording only, in the working tree, not committed and not run.) None of this can be done without a working
shell and Playwright with Chromium.
