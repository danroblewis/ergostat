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

Round 2: built. About 34 net lines of code outside tests (state.py 9, web/server.py 20, web/static/details.js 3).
Each of round 1's findings, and what changed:

- **An actor's "moved" counted zero when its work is measured, not opened** (server.py). The fixer, modeller and
  redesigner write no `valve.opened`. Now "moved" is the sum of the actor's `valve.opened` amounts when there are
  any. When there are none, it is what its valves' flows moved in the window, from `state.moved`: items counted from
  the record (the changes made by the fixer), else from the flow's readings. If any of those flows is unmeasured,
  "moved" is unknown (None), not zero, and the line says "what it moved is not measured".
- **A long-way loop's own flow was always 0** (state.py, server.py, details.js). In `ladder_hints`, the loop's own
  flows are now the flows of the valves it acts on: `lp.valves`, or for a long-way loop its controller's driven
  valves, the same rule as state.py:259 and series.py:291. So `ours` for requests-handled is the
  changes-made-by-fixer rate, and the "keeps up on average: answers too late" branch can be reached again. The panel's
  "moves" row now comes from a new `moves` field in the loop's answer: those same valves' flows and rates. So
  requests-handled shows changes-made-by-fixer, not requests-answered. "Acts but moves nothing" is said only when
  one of those valves' agents ran in the window. When none ran, the hint says "nothing ran to move any". I added
  that so the hint does not claim the loop acted when nothing ran (the finding's "or nothing ran").
- **Tests that could not fail.** The browser fixture is now parametrized: one site where the fixer moved nothing,
  one where 3 of its runs each made a change (expect "moved 3"). Both sites have requests-handled off all the window
  with requests raised at 2/h. Where the fixer made changes at 3/h, the suggestion must say "keeps up on average" and
  not "moves nothing". Where it made none, it must say "acts but moves nothing" and not "per run". The test also
  checks that the loop's moves row names changes-made-by-fixer. The unit hint test now checks both cases: no runs
  ("nothing ran to move any"), then 4 runs of the cleaner ("acts but moves nothing").

Breaks seen to fail, one at a time, each restored: "moved" from valve amounts only (made-changes: "moved nothing"
instead of "moved 3"); the hint's old `mine` (made-changes: "acts but moves nothing" instead of "keeps up"); the
moves row from `lp.rates` (fails on 'never opened' plus 'Moves\nrequests-answered'); `acted` forced true (unit test).

Tests: tests/test_agents_page.py 5 passed, rc 0 (both acceptance cases); tests/test_runner_and_state.py 44 passed;
tests/test_page_polling.py 17 passed, rc 0; ruff clean. Main has no commits beyond the branch base, so there was
nothing to merge.
Left as it is (not asked by the definition): the u chart in the panel still says the fixer's valve "never opened",
because it reads `valve.opened` (series.py), which the fixer never writes. The acceptance check holds: the panel
no longer shows "Moves requests-answered".
Refused in this session: `uv run python -c ...` (a probe of the model), a `python3` heredoc that edits the test file,
and `sed -i ... ; git checkout -- ...` to apply and undo a break. I made the same edits with the editor instead.
Not run here: as in round 1 (test_diagram_rendering.py, test_items_page.py, test_page_refresh.py, the unit suite).

Round 3: the only finding was the conflict with main (720426bd) in tests/test_agents_page.py. Both sides added a
test at the same place: this branch's acceptance test and main's
test_each_group_heading_counts_its_rows_as_the_summary_does. I kept both, each ending with its own
`assert not errors` and `pg.close()`. No code changed in this round.
Tests after the merge: tests/test_agents_page.py 6 passed, rc 0 (both acceptance cases and main's group-heading
test). tests/test_runner_and_state.py and tests/test_page_polling.py: 61 passed, rc 0. ruff is clean.
Refused in this session: `sed -i '182{/^<<<<<<< HEAD$/d}' tests/test_agents_page.py && ...`, which was meant to
remove a conflict marker. I removed it with the editor instead.
Not run here: as in round 1.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:04).

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

Parked by the factory (dead-letters, 2026-11-22 17:04).

Its runs failed past their attempts (a dead letter):
- attempt 14: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 15: nack exited 1
- attempt 16: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 17: nack the run ended with gap/ui-the-evidence-says-in-one-line-whether-the-actor still parked

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 18:30).

Its runs failed past their attempts (a dead letter):
- attempt 15: nack exited 1
- attempt 16: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 17: nack the run ended with gap/ui-the-evidence-says-in-one-line-whether-the-actor still parked
- attempt 18: nack given back
