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
