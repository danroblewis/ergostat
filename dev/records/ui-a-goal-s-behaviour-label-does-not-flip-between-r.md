# ui-a-goal-s-behaviour-label-does-not-flip-between-r: A goal's behaviour label does not flip between reloads, and flapping has a name

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q18 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /loops, loop detail

**The problem:** Labels flip with no change of state ('within its bound' → 'past its bound 4%' → 'within its bound'); 'past its bound 0%' contradicts itself; a goal that crossed its bound 23 times in 32 minutes reads 'holding … Oscillating: no'; 'time off 0%' sits beside 'past its bound 5%'.

**The change:** Apply hysteresis to the behaviour class (it changes only after the new class has held for a set share of the window). Write '<1%', never '0%', for a non-zero share. When crossings pass a threshold the label is 'flapping (23 crossings in 32m)'. Show one share in the row ('time off'), and define 'past its bound' beside it in the detail.

**User stories it serves:** B2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Five reloads of :8791/loops in 60 s: any goal whose status did not change keeps the same behaviour text; no cell contains '0%' next to 'past'; on :8797 a goal with 20 or more crossings in the window shows the word 'flapping' and its count.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1)

Built, all in the page's scripts (`ergostat/web/static/`), about 29 net lines of code:
- **Hysteresis** (`steadyWord`, pages.js): the Loops row's behaviour class (its words without their numbers) changes
  only once the new class has held for 5% of the recorded window (a minute at least); within one class its numbers
  are kept as long. What is shown is kept in `localStorage` by goal, so a reload alone never flips it.
- **'<1%'**: `shareText` (util.js) writes '<1%' for a share that is not zero but rounds to 0%. It is used for time
  off in the row, in the loop detail and under the scope, and for 'past its bound' in the scope.
- **Flapping**: a goal that went off 20 times or more in the window (`FLAP_AT`, util.js; counted from `times_off`)
  reads `flapping (N crossings in W)` in the row, and its detail's time off adds `flapping: N crossings`.
- **One share in the row**: the behaviour cell no longer shows a share ('past its bound', 'saturated' without their
  %); time off is the row's one share. The scope's 'past its bound' now says what it is, beside time off.

Choices made without an answer (the most reversible): the hold share (5%, a minute at least) and the flapping count
(20, from the acceptance) are constants in the page. The count is `times_off`, the goings off that came back in
the window, not a new server field. The hold is remembered in the browser, not on the server. Nothing outside
`ergostat/web/static/` changed.

Test: `tests/test_diagram_rendering.py::test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named` serves a
model and answers `/api/loops` and `/api/loop-control` itself, so the share past the bound flips 4%, 0%, 4% ... over
five reloads with no change of status. Each of three breaks made it fail: no hysteresis ('past'/'within'
alternating), '<1%' turned off, and no flapping. The acceptance names the owner's demos on :8791 and :8797, which are
not reachable here, so the test stands in for them with fabricated answers.

Run: that test, `test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot` and
`tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (3 passed, rc 0, under the watchdog);
`tests/test_web_access.py` (26 passed) and `tests/test_graph_cli_web.py` (31 passed); ruff clean. Not run: the whole
unit suite and the four browser files in full (left to the factory and the merge queue). `main` has not moved since
the clone, so there was nothing to merge.

## Where it stopped (round 2)

Main (277a9c6c) merged in first. Its one conflict was in `tests/test_graph_cli_web.py`, and both sides' tests are kept.

The review's one finding is answered in `steadyWord` (pages.js), with about 3 more net lines of code (about 32 in all):
- A kept word holds a change back only if this browser saw it within the last hold (`seen`, stamped on each use). A
  word that is older than the hold, or has no readable stamp, is stale, and the new word is shown at once. So a browser
  that saw 'within its bound' yesterday shows 'flapping' at once on reopening.
- The key is scoped to the project: `ergostat.behaviour.<S.status.name>.<goal>`, like the sibling keys. A word kept
  for another project, or under the old unscoped key, is never read.

Test: `test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named` now also plants kept words and reloads:
- A kept word seen a second ago still holds a change back.
- A word seen a day ago, plus fresh words under another project's key and the old unscoped key, gives 'flapping
  (23 crossings ...)' at once.

Two breaks each made the test fail: no staleness check (it showed 'within its bound'), and the unscoped key.

Run: that test and `tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (2 passed, rc 0, under the
watchdog); `tests/test_graph_cli_web.py` (33 passed); ruff clean. Not run: the whole unit suite and the four browser
files in full (left to the factory and the merge queue).

## Where it stopped (round 3)

The review's one finding (lesson-9, lesson-8): a kept word went stale after one hold (180 s at a 3600 s window), but an
open page asks for behaviours only every 300 s, so every refresh found it stale and showed the new word at once. Fixed
in `steadyWord` (pages.js), with 0 more net lines of code (still about 32 in all): a kept word is now stale only when
it was not seen within the hold plus two refreshes (`PERF_EVERY`, 300 s, the constant the refresh also uses now). Two
refreshes, not one, so a refresh that comes a few seconds late still finds the word fresh. A word seen a day ago is
still stale, and the new word is shown at once.

Choice made without an answer (the most reversible): the margin of two refreshes is a constant in the page.

Test: `tests/test_diagram_rendering.py::test_a_goals_behaviour_holds_across_refreshes_of_an_open_page` keeps the Loops
page open under Playwright's clock and jumps it forward 301 s three times. Each jump brings a refresh whose answer
flips the share past the bound (4%, 0%, 4%, 0%) with no change of status, and the behaviour text stays the same. With
the old limit (the hold alone) put back, it failed: `['past its bound', 'within its bound', 'past its bound', 'within
its bound']`.

Run: the new test, `test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named` and
`tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (3 passed, rc 0, under the watchdog);
`tests/test_graph_cli_web.py` (33 passed); ruff clean. Not run: the whole unit suite and the four browser files in full
(left to the factory and the merge queue). `main` is still 277a9c6c, already merged in, so there was nothing to merge.
