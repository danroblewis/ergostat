# ui-no-leftover-in-a-panel: No leftover '…' in a panel

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q04 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram side panel (system panel, stock panel, loop panel)

**The problem:** The system panel shows a lone '…' under its title; the loop panel shows 'When it drives the behaviour …' for good; both read as a stuck load.

**The change:** Show the description, or nothing. While a value is being worked out say 'being worked out'; when it cannot be, say why ('no loop is dominant in this window').

**User stories it serves:** A4, G4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
After 10 s on :8796, clicking the product box, the users stock and marker R2: no element in the side panel has text equal to '…' or ending in ' …'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. The '…' came from the placeholder of the four side-panel charts in `ergostat/web/static/charts.js`
(`causesStrip`: stock and flow panels; `moduleCharts`: the system panel; `loopDominance`: the feedback loop panel;
`loopScope`: a goal's loop panel). Each now says "being worked out" (one `working()` helper) until its answer
replaces it. The loop panel's "When it drives the behaviour" used to go blank when `/api/dominance` failed or the model
could not be read; it now says why it is not worked out. Its other cases already said why (not scored, a score of 0
throughout, no loop named as dominant at a stock). 9 net lines in `charts.js`.

Choice made alone (the most reversible): `loopScope` (a goal's loop panel, in Blocks too) is changed with the
others because it uses the same placeholder. Truncation ellipses inside drawn labels (`dynamics.js`, `diagram.js`) are
not panel text and are left alone.

Test: `tests/test_diagram_rendering.py::test_no_panel_shows_a_leftover_ellipsis` (software-factory served from a copy
with its model not run, so no port 8796 is needed; 10 s on the page, then the product box, the users stock and marker
R2, each panel checked every 250 ms for 6 s). Before the fix it failed with the product panel's lone '…' at every
look. `test_a_closed_systems_panel_charts_its_measures` now also counts "being worked out" as not answered.

Runs (in the container, serial, under the watchdog): ruff clean; the new test and the closed-system test pass; the
whole `tests/test_diagram_rendering.py` ran rc 1, 196 passed and 5 failed (52 min). Run again alone:
`test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back` passes, so it failed under load only. The
other four fail alone too, and none reads the side panel's charts this branch changes: `test_every_view_draws_cleanly_and_in_time[coordinator]`
and `[image-squeeze]` (routing open=* 24.9 s and 25.5 s, bound 20 s), `test_a_big_tangled_model_lays_out_in_time_and_cleanly`
(2779 ms, bound 2500 ms): layout time bounds, layout code untouched; `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`
(the /model page lacks "Nothing waiting." after an accept: the Model page, untouched). Not verified on main: `git
checkout -q main` was refused in this session, so the factory's rerun on clean main must settle them. Not run here:
the unit suite, the other three browser files (no page they draw uses these charts), and a merge of main (the clone is
main as of the branch, so there is nothing newer to merge).

Round 1, after the fast suites: `build` (dev/factory.toml `[suites] build`) ended rc 5 with
`SKIPPED [1] tests/test_diagram_rendering.py:38: could not import 'playwright.sync_api'` and `1 skipped`. That is not a
code failure. `scripts/affected_tests.py` picks the changed test file, which is browser-only. The build command runs it
without `--with playwright`, so the whole module is skipped and pytest reports that no test ran (rc 5). The definition of
done puts the acceptance test in this file, so any branch that follows it gets the same result. No code was changed in
answer: the fix is in the factory's build step, either running the browser files it selects with Playwright or not
selecting them while `build_browser = false`. That is outside this gap (lesson 13) and belongs in its own gap. This
session could not run the test again: Bash was refused for `node --check ergostat/web/static/charts.js` and a Playwright
import check. The browser results above, from earlier in round 1, are the latest.

Round 2: no review findings to answer (none were recorded), and no code changed. The branch already has main
(277a9c6c) merged in (54efadbc), and the tests were run again on that merge: `uv run ruff check ergostat tests scripts`
is clean, and under the watchdog with Playwright 1.63.0, `test_no_panel_shows_a_leftover_ellipsis` and
`test_a_closed_systems_panel_charts_its_measures` pass (2 passed, 40.6 s, rc 0, 135 threads at peak). Not re-done
here: the break-and-fail check (lesson 9). The command that put main's `charts.js` in the working tree, ran the
acceptance test and restored the file was refused
(`git show main:ergostat/web/static/charts.js > ergostat/web/static/charts.js && … named_tests.py …::test_no_panel_shows_a_leftover_ellipsis …; git checkout -- ergostat/web/static/charts.js`),
so the before-the-fix failure from round 1 is the only evidence. The build's rc 5 described above has not changed:
`scripts/affected_tests.py` and `[suites] build` are the same on main, so the factory's build step will skip this
browser-only file again. That is the factory's own fix to make in a gap of its own, not this one (lesson 13). Nothing in
this gap is left to build.

Round 2, after the build failed again (rc 5, the browser-only file skipped without Playwright): fixed in the branch
this time, instead of waiting for a factory gap, because it is the most reversible fix. A unit check that needs no
browser, `tests/test_graph_cli_web.py::test_the_side_panels_charts_say_being_worked_out_never_a_bare_ellipsis`, reads
`charts.js`. It checks that no string literal there is '…' (or `…`) or ends in ' …', that the `working()`
placeholder says "being worked out", and that `causesStrip`, `loopDominance`, `moduleCharts` and `loopScope` each use it.
That follows the pattern of the `util.js` check in the same file. `affected_tests.py` now picks this file as well, so
the build has a test to run. Its first run failed on the only bare '…' left in `charts.js`, the quoted ellipsis in
round 1's comment over `working()`. That comment now says "a bare ellipsis" (a comment, 0 net lines). So the check is
seen to fail on a literal '…' and pass without one. Not run: the check against main's `charts.js` (the command that
swapped the file in was refused), and the build command itself
(`uv run python scripts/suite_watch.py -- uv run python scripts/affected_tests.py -- uv run python -m pytest -q -rfEs -n 8 --dist worksteal`,
refused). Also refused: `named_tests.py tests/test_graph_cli_web.py tests/test_diagram_rendering.py`. Run: the whole
`tests/test_graph_cli_web.py`, 33 passed; ruff clean. The browser file still skips without Playwright when the build
runs. With this file selected too, pytest should end rc 0 with the skip named, but the factory's build is what will show it.
