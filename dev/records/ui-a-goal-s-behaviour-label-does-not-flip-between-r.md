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

## Where it stopped (round 4)

The queue's one finding: the merge of main (2a97eafb) conflicted in three files. All are resolved, and both sides are kept:
- `control.js`: main wraps the scope's 'past its bound' in `ofRecorded` ("of the time" → "of the N recorded"). The
  branch writes its shares through `shareText` and adds the definition. Both are kept: `ofRecorded` wraps the
  measured part, and the definition follows it. No net lines added.
- `tests/test_graph_cli_web.py`: the branch's source check and main's `/api/status` goals-off test are both kept.
- `tests/test_diagram_rendering.py`: the branch's two behaviour tests and main's `goal_named` helper and its
  goal-name test are each kept whole. The branch's test of the scope's text now accepts either "of the time" or main's
  "of the N recorded".

No other review findings were open.

Run: `test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named`,
`test_a_goals_behaviour_holds_across_refreshes_of_an_open_page` and main's
`test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction` (both cases): 4 passed, rc 0, under
the watchdog. `test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot` and
`tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` also passed (2 passed, rc 0).
`tests/test_graph_cli_web.py`: 41 passed. Ruff is clean. Not run: the whole unit suite and the four browser files in
full (left to the factory and the merge queue).

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:07).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:07).

Its runs failed past their attempts (a dead letter):
- attempt 29: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 30: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 31: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 32: nack the run ended with gap/ui-a-goal-s-behaviour-label-does-not-flip-between-r still parked

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:23).

Its runs failed past their attempts (a dead letter):
- attempt 30: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 31: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 32: nack the run ended with gap/ui-a-goal-s-behaviour-label-does-not-flip-between-r still parked
- attempt 33: nack the implementor pool is full (run/pools.json): waits its turn

## Where it stopped (continued, round 1)

The merge of main (63998238) conflicted in two files. Both are resolved, and both sides are kept:
- `pages.js`: main replaced the Loops row's error column (`e = r − y`) with 'how far' (`off_by_words`, `data-off`).
  The branch writes time off through `shareText` ('<1%'). Kept: main's 'how far' cell, and time off through
  `shareText`.
- `details.js`: main replaced the loop detail's 'error' row with 'how far'. The branch writes time off through
  `shareText` and adds `flapping: N crossings`. Kept: main's 'how far' row, and the branch's time off.
No net lines added. No review findings were open.

Run: `test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named`,
`test_a_goals_behaviour_holds_across_refreshes_of_an_open_page` and main's
`test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks` (3 passed, rc 0, under the watchdog);
`tests/test_graph_cli_web.py` (41 passed); ruff clean. Not run: the whole unit suite and the four browser files in
full (left to the factory and the merge queue).

## Where it stopped (continued, round 2)

The merge of main (7cb97857) conflicted in `pages.js`. Main moved each loop's behaviour into `/api/loops?perf=1`
(worked out on the server in the background, again every 5 minutes, `PERF_LIFE`). The page no longer asks
`/api/loop-control` for each loop every 5 minutes. Both sides are kept:
- Main's one answer, its `lp.points` trend, and its 'being worked out' / 'could not be worked out' words.
- The branch's hysteresis and flapping now sit in main's `word()`. A goal with 20 crossings or more reads
  `flapping (N crossings in W)` through `steadyWord`. Any other analysed behaviour goes through `steadyWord` too.
  'Being worked out' is shown as it is. `PERF_EVERY` (300 s) still sets the stale margin and matches the server's
  `PERF_LIFE`.
- About 1 more net line of code (about 33 in all).

Tests changed to match: the two behaviour tests now give `perf` inside their mocked `/api/loops` answer, not through
`/api/loop-control`. In `tests/test_graph_cli_web.py`, the source check's pattern follows the merged line. Each
behaviour test was seen to fail with a break: with no hysteresis, the reload test showed
`['past its bound', 'within its bound', ...]`; with the stale limit set back to the hold alone, the open-page test
showed `['past its bound', 'within its bound', 'past its bound', 'within its bound']`.

Run: both behaviour tests and main's `test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks`
(3 passed, rc 0, under the watchdog); `tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (passed);
`tests/test_graph_cli_web.py` (41 passed); ruff clean. Not run: the whole unit suite and the four browser files in
full (left to the factory and the merge queue).

## Where it stopped (continued, round 3)

The review's one finding (lesson-8, lesson-9): `steadyWord` held the kept live word back on a past moment (`S.at`),
and saved the past word under the live key. Fixed in `steadyWord` (pages.js) with 1 more net line of code (about 34
in all): on a past moment it returns the moment's own word at once and reads and writes nothing. The hold applies only
to the live view, where it was asked for. The live word stays kept, so going back to live is held as before.

Choice made without an answer (the most reversible): no hysteresis on a past moment, not a separate kept word for
each moment. A past view's answer never changes, so there is nothing to smooth there.

Test: `tests/test_diagram_rendering.py::test_a_past_moment_shows_its_own_behaviour_at_once_and_keeps_the_live_one`.
It loads /loops live ('within its bound', kept), then sets `S.at` ten minutes back and routes. That moment's answer is
'past its bound', and the test sees it within 5 s, well inside the 60 s hold. The kept live word is unchanged. Back to
live, the row reads 'within its bound' again. With the fix removed, it failed: the cell stayed 'within its bound'
(a wait_for_function timeout).

Run: the new test and both earlier behaviour tests (3 passed, rc 0, under the watchdog); `tests/test_graph_cli_web.py`
(41 passed); ruff clean. Not run: the whole unit suite and the four browser files in full (left to the factory and the
merge queue). `main` is still 7cb97857, already merged in, so there was nothing to merge.

## Where it stopped (continued, round 4)

The merge of main (ead497d1) conflicted in three files. All are resolved, and both sides are kept:
- `pages.js`: main writes the Loops row's hold through `holdText` and names a limit in the 'how far' title
  (`isLimit`). The branch writes time off through `shareText` ('<1%'). Kept: main's two cells, and time off through
  `shareText`. No net lines added.
- `tests/test_graph_cli_web.py`: the branch's source check and main's record-fold check are both kept.
- `tests/test_diagram_rendering.py`: the branch's three behaviour tests and main's `off_for` helper are each kept
  whole. The last behaviour test's `finally` (stop the server) was shared with `off_for` in the conflict, so each now
  has its own.

No review findings were open.

Run: the three behaviour tests (3 passed, rc 0, under the watchdog); main's
`test_a_suggestion_appears_when_it_has_a_verdict` and `test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks`
(2 passed, rc 0, under the watchdog); `tests/test_graph_cli_web.py` (43 passed); ruff clean. Not run: the whole unit
suite and the four browser files in full (left to the factory and the merge queue).

## Where it stopped (continued, round 5)

The merge of main (5411f137) conflicted in `pages.js`, on the Loops row's last two cells. Main gives each table a
caption (the `table(..., "", "Loops")` arguments) and a `<tbody>`. The branch's behaviour cell calls `word(n, lp)`
(hysteresis and flapping) and has a longer title. Both are kept: the branch's cell, closed with main's caption
arguments. No net lines added. No review findings were open.

Run: the three behaviour tests (3 passed, rc 0, under the watchdog); `tests/test_graph_cli_web.py` (43 passed); ruff
clean. Not run: the whole unit suite and the four browser files in full (left to the factory and the merge queue).

## Where it stopped (continued, round 6)

The merge of main (e43046dc) conflicted in three files. All are resolved, and both sides are kept:
- `charts.js`: main keys the scope's off stretch with `offKey()` (no 'Red: off'). The branch writes time off through
  `shareText`. Both are kept.
- `pages.js`: main also asks `/api/systems` for its quiet lines. The branch's `word(n, lp)` (hysteresis and
  flapping) is kept. Both are kept: main's two asks, then the branch's `st`/`win` and `word`.
- `tests/test_diagram_rendering.py`: the branch's three behaviour tests and main's `OFF_PIXELS`, `CONTRAST` and
  hatched-off test are each kept whole. Each test has its own server set-up and `finally`.
No net lines added. No review findings were open (the queue's one finding was this conflict).

Run: the three behaviour tests (3 passed, rc 0, under the watchdog); main's
`test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes` and
`tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (2 passed, rc 0, under the watchdog);
`tests/test_graph_cli_web.py` (45 passed); ruff clean. Not run: the whole unit suite and the four browser files in
full (left to the factory and the merge queue).

## Where it stopped (continued, round 7)

The review's one finding (lesson-5): the kept word was keyed by project and goal, not by window. After a change of
window, the old window's word, with its count and span, was held for a hold of the new window. On the first render
after the change, `win` was also the header's old `S.status.window`. Fixed in pages.js, with 1 more net line of code
(about 35 in all):
- The key is now `ergostat.behaviour.<project>.<S.since>.<goal>`, so each window keeps its own word. A word kept for
  another window is never read.
- `win` comes from the chosen window (`WINDOWS[S.since]`, the header's `S.status.window` if that is unknown),
  clipped to the recorded span as before. So the first render after a change already states the new window's span.

Choice made without an answer (the most reversible): a kept word for each window, not a reset on a change of window.
Going back to a window shows that window's own kept word, held as before.

Test: `tests/test_diagram_rendering.py::test_a_change_of_window_shows_that_windows_behaviour_at_once`. Over ten
minutes the mocked goal is 'within its bound' (kept). Switched to a day (as the window menu does), where it went off
23 times, it reads `flapping (23 crossings in <the day's recorded span>)` within 5 s. Back to ten minutes, it reads
'within its bound' at once, and each window's kept word is its own. Each break made it fail:
- The unscoped key put back: a wait_for_function timeout (the old 'within' was held).
- The header's `st.window` put back: `['flapping (23 crossings in 10m)', 'flapping (23 crossings in 40m)']`.

The other behaviour tests now read the kept word under the window's key.

Run: the new test, `test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named` and
`test_a_past_moment_shows_its_own_behaviour_at_once_and_keeps_the_live_one` (3 passed, rc 0, under the watchdog);
`test_a_goals_behaviour_holds_across_refreshes_of_an_open_page` and
`tests/test_page_polling.py::test_leaving_a_page_stops_its_polling` (2 passed, rc 0, under the watchdog);
`tests/test_graph_cli_web.py` (45 passed); ruff clean. Not run: the whole unit suite and the four browser files in
full (left to the factory and the merge queue). `main` is still 1c790d38, already merged in, so there was nothing to
merge.
