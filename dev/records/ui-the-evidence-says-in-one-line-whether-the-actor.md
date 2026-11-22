# ui-the-evidence-says-in-one-line-whether-the-actor: The evidence says in one line whether the actor was commanded, ran and moved anything

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q28 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** goal evidence panel; /agents rows of rules

**The problem:** requests-handled: 'u: never opened. Its valve did not open' beside 'Moves requests-answered 1.62/h' and a suggestion to do 'more per run'; Agents shows fixer with 34 runs; the Record shows it commanded every minute; its log says 'no open request the rule tier answers'. keep-requests-handled reads 'no roles, not run here'. A sensor reads 'unfilled' beside 'read 2s ago: 36'.

**The change:** Build the actor lines from the same counts Agents and the Record use: 'fixer: commanded 34 times, ran 34, moved nothing (its log: no open request the rule tier answers)'. Show 'Moves' only for what this goal's own valve moved. When it moved nothing the suggestion says 'acts but moves nothing', not 'more per run'. Give each keep-* rule its controller role on Agents. Drop 'unfilled' when a reading exists.

**User stories it serves:** C3, C2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791 the evidence for requests-handled contains 'commanded' and 'ran' with numbers equal to the fixer's run count on /agents for the same window; it does not contain both 'never opened' and 'Moves requests-answered'; the Agents row keep-requests-handled contains 'controller'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built. About 32 net lines of code outside tests (state.py, web/server.py, web/static/details.js).

- **Actor lines.** The loop panel (the goal's evidence, opened by "Evidence" or a /loops row) gets one line per actor.
  The actors are the agents of the valves the controller drives, plus the machine blocks that name the goal. Each line
  is "NAME: commanded N times, ran N, moved X | moved nothing (its log: LAST LINE)". `ran` is the same number the
  /agents row shows (`snap["agents"][a]["runs"]`, same window). `commanded` counts `block.commanded` in the window.
  `moved` sums the `valve.opened` amounts of the actor's valves. The log line is the last line of the last run's
  entry in `logs/NAME.log` (web/server.py, loops/NAME).
- **Moves.** The panel's "moves" row shows only when the loop has a valve of its own (`lp.valves`). A loop that
  closes the long way (requests-handled, through the judge) no longer shows the far flow as its own.
- **Suggestion.** In `state.ladder_hints`, what the loop moved is read only from its own valves' flows. When that is
  zero, the hint says "it acts but moves nothing ... while X/h came in", not "More per run". The hint is built
  in state.py, outside "Files to touch", because the page only shows the text the snapshot gives it.
- **keep-\* on Agents.** An implied `keep-GOAL` onoff block gets the role `controller GOAL` in the snapshot's agent
  roles (state.py; the CLI's `ergostat agents` shows it too, from the same snapshot). This is outside "Files to
  touch" for the same reason. I chose the most reversible option: add the role in the snapshot rather than change
  which agent `spec/legacy.to_model` makes the controller's (the fixer stays the controller's agent there, so
  nothing that reads `Controller.agent` changes). Its "last run" cell still says "not run here": the definition did
  not ask to change it.
- **unfilled.** A sensor with a reading and no agent shows no "unfilled": in the loop's parts table and in the
  sensor's own panel.

Tests: tests/test_agents_page.py::test_the_evidence_says_in_one_line_whether_the_actor_was_commanded_ran_and_moved_anything
(the modelling template, 34 commanded runs of the fixer, its log, one reading; 4 passed in the file, rc 0) and
tests/test_runner_and_state.py::test_a_loop_whose_valve_moves_nothing_acts_but_moves_nothing_not_more_per_run (44
passed). The acceptance test is in the Agents page's own browser file, which the definition allows; it is not one
of the four browser files. I broke each guarded piece once and saw the tests fail: the old "moves" row (fails on
'never opened' plus 'Moves\nrequests-answered', the review's own text), no keep-\* role ("no roles"), a wrong
`ran`, "unfilled" put back, and the hint's old branch ("More per run, or acting more often").
tests/test_page_polling.py: 17 passed, rc 0. ruff is clean. Main has no commits beyond the branch base, so there
was nothing to merge.

Not fixed (outside the gap; lesson 13):
tests/test_diagram_rendering.py::test_every_part_opens_its_panel_when_clicked_even_mid_redraw fails on this branch
in 2 of 2 runs: `stock:awaiting-deploy` and `stock:bugs-live` open no panel when clicked. I could not run it on
main: `git checkout -q main` was refused. Nothing this branch changes is on a stock panel's path. The other two
panel tests passed with it (test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot and
test_a_loop_marker_lights_its_loop_and_opens_its_panel). The factory should run it on clean main.
Not run here: the rest of test_diagram_rendering.py, test_items_page.py and test_page_refresh.py, the unit suite,
and demo_check (no example touched).
