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
