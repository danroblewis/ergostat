# ui-on-a-phone-each-goal-is-a-card-value-against-bou: On a phone each goal is a card: value against bound, and how long off

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q72 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /loops at ≤ 760 px

**The problem:** The table is 943 px wide in 358 px: loop, status and holds show; now, setpoint, error and time off are off to the right with no cue. 'Time off' is a share of the window, not how long the goal has been off.

**The change:** Below 760 px each row is a two-line card: 'requests-handled · off' then '36 against ≤ 0 · off 36m · usually back in 30s'. Off goals first. No sideways scroll.

**User stories it serves:** H4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 390x844 on :8791/loops, in light and dark, each off goal's card shows its value, its bound and a duration within the viewport's width; the page's scrollWidth equals its clientWidth.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1 (15 net lines outside tests). Choices taken without anyone to ask, each the most reversible:
- How long a goal has been off was not in the page's answer, only the share of the window. `ergostat/state.py` (outside
  `ergostat/web/`) gains two keys on each loop: `off_since`, when its current off spell began, and `off_before_window`,
  so a spell that began before the window reads 'off over 6h'. An off goal with no recorded crossing reads 'off since ?'.
- The card is one more cell in each row of the same table, shown alone below 760 px by CSS. There is still one table,
  the rows keep their keys and row click, and the desktop table is unchanged. Off goals come first by the page's existing
  order. The card's bound is the setpoint without its tolerance band, as in the change's example.

Acceptance test: tests/test_diagram_rendering.py::test_on_a_phone_each_goal_is_a_card_its_value_against_its_bound_and_how_long_off
(passes). Three breaks were each seen to fail it: the phone rule off (760 → 300 px), the other cells left visible, and
the duration left out of the card.
The whole of tests/test_diagram_rendering.py ran serially under the watchdog: 196 passed, 5 failed. Four are the
failures earlier reviews found on main (coordinator and image-squeeze routing time, the big tangled model, the
'Nothing waiting.' equation test). The fifth, test_a_valve_turns_upright_when_its_pipe_runs_up, draws a Dynamics valve
this change does not touch, and it passed when rerun alone. The other three browser files and the unit suite were
not run here.

Build step, round 1: `[suites] build` ran only tests/test_diagram_rendering.py (state.py has no tests/test_state.py).
Without Playwright that file skips, so the run ended rc 5 with nothing run. The state.py change had no unit test of its
own. tests/test_runner_and_state.py::test_a_loop_off_now_says_since_when_and_whether_the_spell_began_before_the_window
now covers `off_since` and `off_before_window`, and it was seen to fail when `<=` was broken to `<`. That file passes:
44 tests.

Round 2. The one finding (pages.js: 'off <duration>' measured to wall-clock now while the snapshot is as of a chosen
past moment) is fixed: the duration now runs to `S.at || nowS()`, the moment the answer is as of (+1 net line in
pages.js, so 16 net lines outside tests in all). The acceptance test now also sets a past moment half an hour back, as
the time slider does (`S.at`, then `route()`), and expects '36 against ≤ 0 · off 6m · usually back in 30s'. It passes,
and with the fix taken out (`nowS()` alone) it failed (the card read 'off 36m'). ruff is clean.
Not run in round 2: the whole of tests/test_diagram_rendering.py. A first run was stopped at the session's 20-minute
background time limit before it ended, with no result. The rerun with a longer limit
(`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/drender.log 2>&1`)
was refused in this session. The round-1 full-file result above is the latest. The other three browser files and the
unit suite were not run.

Round 3. The one finding, a conflict with main in tests/test_diagram_rendering.py, is resolved in the merge of main
(bea24a23): main's new test (test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction, with
its goal_named, RINGED and TITLED) and this branch's phone-card test had been added at the same place and shared one
server start-up tail. Each is now a whole function of its own, main's first, both waiting up to 300 tries for the server
as main does. No code outside tests changed in this round. The card stays the last cell of each row, so main's rule
that each row's first cell is the name button holds. After the merge: ruff is clean; the phone-card test and both cases
of main's test pass (3 passed, under the watchdog with Playwright); tests/test_runner_and_state.py passes (44).
Not run in round 3: the whole of tests/test_diagram_rendering.py. The background run
(`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/drender.log 2>&1; echo done >> /tmp/drender.log`)
was refused in this session. The other three browser files and the unit suite were not run either.

Round 4. The one finding, conflicts with main in ergostat/web/static/pages.js and tests/test_diagram_rendering.py, is
resolved in the merge of main (ead497d1, merge commit 9919deaa). pages.js keeps main's Loops page whole: one `loops`
answer with `perf=1`, the trend from `lp.points`, the 'r' and 'how far' columns, `word(lp.perf)`. The branch adds only
its `offFor`/`card` helpers, the card cell at the end of each row and the table's `loops` class. The earlier per-loop
`perf` polling the branch had kept from old main is gone, as main removed it. In the test file, main's new
test_a_suggestion_appears_when_it_has_a_verdict (with HINTS, LOOP_ENTRY, CAUSE) and the phone-card test are each whole
and separate. No code changed beyond the merge. Net lines outside tests stay at 16.
After the merge: ruff is clean; the phone-card test and
test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[True] pass;
tests/test_runner_and_state.py passes (45).
Fails, twice in a row: test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False], at
line 3118. The diagram side panel's `.side .suggest .hint button.name` is never visible. That is the diagram's
Suggestions fold, which this branch does not touch (the branch's CSS is scoped to `table.loops`, and its pages.js change
is the Loops page's card). The test passed here in round 3, before this merge brought main's change that holds a
suggestion back until ten minutes of record (test_a_suggestion_appears_when_it_has_a_verdict). So the likely cause is
two of main's changes meeting, not this branch. Checking it on clean main (`git archive main | tar -x -C /tmp/mainck`
and the same test there) was refused in this session, so that is not confirmed.
Not run: the whole of tests/test_diagram_rendering.py, the other three browser files and the unit suite.

Round 5. The one finding, a conflict with main in ergostat/web/static/pages.js, is resolved in the merge of main
(dc47a763, merge commit 3374e557). Main now draws each goal's row through one renderer, goalrow.js (`goalRow`,
`GOAL_CELLS`), and test_graph_cli_web.py::test_no_page_script_words_a_goals_state_but_goalrow bars any other script
from wording a goal's state (`statusEl(lp.status)`, `lp.status !== "off"`). So the card moves from pages.js into
goalrow.js as one more cell, `GOAL_CELLS.card`, with its helper `goalOffFor`. Both now read `goalWord(g)` instead of
the status. The Loops page keeps main's code whole (the quiet-systems lines, `goalRank`, `goalRow` with its columns)
and adds only `"card"` to its columns and the table's `loops` class. Nothing else changed. Net lines outside tests:
14 (state.py 1, goalrow.js 7, style.css 6, pages.js 0).
After the merge: ruff is clean; test_no_page_script_words_a_goals_state_but_goalrow passes; tests/test_runner_and_state.py
passes (47); the phone-card test passes, and with `"card"` taken out of the columns it failed (Playwright timeout). Also
passing: test_the_goals_page_says_each_goals_word_as_the_server_does_live_and_from_a_snapshot,
test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks and
test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[True].
Still fails, as in round 4: test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False],
now at line 3544 (`.side .suggest .hint button.name` click times out). That is the diagram's Suggestions fold, which
this branch does not touch (lesson 13: reported, not fixed). Two checks were refused in this session, so this is not
confirmed on clean main: `git worktree add --detach /tmp/mainck main` with the same test run there, and the whole-file
background run (`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/drender.log 2>&1`).
Not run: the whole of tests/test_diagram_rendering.py, the other three browser files and the unit suite.
