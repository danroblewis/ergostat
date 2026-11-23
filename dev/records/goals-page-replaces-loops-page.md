# goals-page-replaces-loops-page: The Loops page becomes Goals, and every reader-facing 'loop' that means a goal says 'goal'

depends-on: []

Problem: one word names both the goal and the R/B and control structures. On :8796 the header reads '2 loops off' and /loops shows h1 'Loops' with first column 'loop' (shots/plan-goalvocab-sf-loops.png); Blocks' side list is headed 'Loops 25' over goals while Dynamics lists 'Feedback loops 49' (plan-goalvocab-8792-blocks.png); the glossary entry that opens a goal's panel (ergostat/web/static/details.js:27) reads loop: ['Feedback loop', 'a goal on a stock and what serves it...']. The owner: 'when I open the loops page I know it actually means goal'.
Change (words a reader sees, routes and docs only; internal names pageLoops, openLoop, .looprow, data-loop, snap['loops'] stay so filed Q16, Q18, Q72 still apply):
- Routes: /goals in UI_PAGES (web/server.py:35, util.js:15) and OTHER_PAGES (split.js:26); router (util.js:508-510) maps /goals to the page and redirects /loops to /goals keeping its query, as /fit goes to /model; the phone start page is /goals (main.js:53).
- Nav: index.html:13 'Goals'. Page (pages.js:20-63): h1 'Goals', first column 'goal', tooltip 'the share of the window the goal spent off'.
- Header (util.js:374): 'N goal(s) off'. diagram.js:1362 'N more on Goals'. Blocks side-list heading (diagram.js:1382): 'Goals and their control loops' (its rows are goals; leave to Q62 if it landed).
- Goal panel (details.js:140-141): kind 'Goal' or 'Goal, open loop'; WHAT gains goal: ['Goal', 'what is wanted of a stock (its bound) and whether it holds; its control loop (sensor, controller, valve) serves it']; WHAT.loop goes; control.js:190-227 'The loop X' becomes 'The control loop of goal X'.
- Legends: diagram.js:1013, export.js:67,72 ('goal holding'). Model page heading review.js:395 'Control loops'.
- CLI: table headers LOOP/LOOPS become GOAL/GOALS (cli/system.py, cli/status.py, cli/running.py); the lines that print 'loop NAME holding' become 'goal NAME holding' (ergostat/show.py:76, 191, 199; cli/system.py:98); the stale 'no loops: a loop is a [[controller]]' becomes 'no goals: a goal is a goals: entry holding a stock'.
- The Guide (ergostat/guide.py): checked, its frames use 'loop' only for R/B feedback loops and control loops; the builder verifies this with a grep recorded in the PR and changes any reader text that means a goal; frame identifiers and code stay.
- Docs: docs/vocabulary.md:155 row 'Goal (holding, off), served by a control loop' plus a line that 'loop' alone is never a goal, and a short section 'Items and leases' fixing three words for the gaps that follow: a goal is 'holding'; an item a block has leased is 'taken' or 'being worked by <block>' (never 'held'); an item the estimates leave out is 'not scheduled'. QUICKSTART.md:53, DISCIPLINES.md:30, DESIGN.md:130,249,266,300,303, SPEC.md:4306,4376, README.md:217,227.
- Must not change: event types loop.off/loop.holding; /api/loops, /api/loops/NAME and the JSON key loops (no alias); loop-scope, loop-control, around=loop/NAME, causalLoops, SD_WHAT.loop (dynamics.js:543), the Guide's frame identifiers, localStorage ergostat.loops, the `ergostat loop` command, YAML keys goals:/loops:/open_loop.
Definition of done:
1. :8796/goals shows h1 'Goals' with first column 'goal'; the nav has 'Goals' and no 'Loops'.
2. :8796/loops?status=off lands on /goals?status=off with the same rows.
3. No element in the header contains 'loop'; a goal's panel shows kind 'Goal'; a controller block's panel in Blocks still says 'control loop'; 'Feedback loops' is still the Dynamics heading.
4. grep finds no 'Loops page' in docs/ or README.md, and no 'loop {name} holding|off' format string in ergostat/show.py or ergostat/cli/.
5. docs/vocabulary.md has the 'Items and leases' section.
6. The record and spec are unchanged (tests reading loop.off pass unedited).
Files: ergostat/web/server.py, ergostat/web/static/{index.html,util.js,split.js,main.js,pages.js,diagram.js,details.js,control.js,export.js,review.js}, ergostat/cli/{system.py,status.py,running.py}, ergostat/show.py, ergostat/guide.py (only if the check finds a goal called a loop), the docs above, tests/test_graph_cli_web.py:212, tests/test_page_polling.py:174-176, tests/test_diagram_rendering.py:2340, scripts/scale_bench.py:508.
Acceptance tests: the four tests visit /goals; one asserts /loops still answers and redirects; a CLI test of `ergostat show` printing 'goal'; tests/test_diagram_rendering.py passes in full.
Budget: 70 net code lines (mostly strings), 35 of docs, 20 of tests.

Milestone: goals-not-loops. Owner items: Decision: 'goal' instead of 'loop' for what is held or off; the Loops page becomes Goals; 'feedback loop' and 'control loop' stay (delivers R11 pieces 2-3). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (round 1): /goals is the page (server and util.js UI_PAGES, split.js OTHER_PAGES, router, phone start); /loops is
kept in both lists and redirects to /goals with its query, as /fit does to /model. Nav, h1, first column, tooltip,
header ('N goal(s) off'), '… more on Goals', Blocks side list 'Goals and their control loops' / 'No goals in view.',
legends ('a goal off', export 'goal holding'), goal panel kind 'Goal' / 'Goal, open loop' with WHAT.goal (WHAT.loop
gone; the controller panel shows WHAT.goal too), control.js 'The control loop of goal X', review.js 'Control loops'.
CLI: GOAL/GOALS headers, 'goal NAME' lines (show.py, system.py incl. `loop NAME` and the cycles line), 'no goals: a
goal is a goals: entry holding a stock', 'no goal X; goals: …'. Docs as listed, plus every other 'Loops page' in docs/
(MODEL-TOOLS.md, proposals/charts.md, proposals/coordinator/09-operator-interface.md, cli-rounds.md:337) so the DoD 4
grep holds; vocabulary.md row, the "'loop' alone is never a goal" line and 'Items and leases'.

Choices taken without asking (the most reversible):
- blocks.js (not in Files): a controller block's panel heading 'In the loop of X' became 'In the control loop of X';
  without it the Blocks controller panel did not say 'control loop' (DoD 3).
- There is no `ergostat show` command; the CLI acceptance test is
  tests/test_graph_cli_web.py::test_the_cli_calls_what_is_held_a_goal, over the commands that print through show.py
  (`system host`, `system host --blocks`, `loop NAME`, `loop`).
- Left alone, not in the definition: state.attention's 'loop NAME' ('what') lines and the diagram's /^loop (\S+)/ parse
  of them (many tests read them); a system box's 'N loops: 2 holding' (diagram.js loopsText, details.js openSystem).
  Both still call goals loops; a follow-up gap should rename them.

Guide check (ergostat/guide.py): `grep -nw -E 'loops?' ergostat/guide.py` gives lines 21, 55, 65, 152, 166, 177, 185,
197, 215, 220, 227, 257. Reader text: 166 'closes a loop. B balances', 185 'R reinforces … The loop that dominates', 215
'Close the loop: a sensor H', 220 'the loop pushes it back', 227 'the inner loop's setpoint', 65 'the inner loop,
holding the signup rate' are R/B feedback loops or control loops; the rest are code/keys. No goal is called a loop, so
guide.py is unchanged.

Tests run: ruff clean; tests/test_graph_cli_web.py 33 passed; tests/test_page_polling.py 18 passed (incl. the new
test_the_goals_page_and_its_old_address, and test_leaving_a_page_stops_its_polling on /goals). The new browser test was
seen to fail with the /loops redirect removed (TimeoutError) and with the panel kind put back to 'Loop'.
tests/test_diagram_rendering.py in full: 195 passed, 5 failed. Rerun one at a time: the pinned-block test passed;
test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze] failed again on time only (routing open=*
24.5 s and 26.5 s, bound 20 s); test_a_big_tangled_model_lays_out_in_time_and_cleanly on time (2899 ms, bound 2500 ms);
test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page on 'Nothing waiting.' missing from the
Model page (pages.js:1093, untouched here; the same failure is reported in other branches' reviews). I believe all four
are unrelated (load-dependent bounds and a main-side failure), but this is NOT proven: running them on clean main was
refused here (`git checkout -q main && … named_tests.py …`). The merge queue should run them on main.
Not run: the unit suite and the other browser files (left to the factory, as told).

Overrun reason: tests are net +44 lines against a test budget of 20: the one browser acceptance test checks every
point of DoD 1-3 (page, nav, redirect with query and same rows, header, goal panel, Blocks controller panel and side
list, Dynamics heading) and the CLI test covers four commands; code is net +1 (budget 70), docs net +12 (budget 35).

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
- attempt 8: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 9: nack exited 1
- attempt 10: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 11: nack the run ended with gap/goals-page-replaces-loops-page still parked
