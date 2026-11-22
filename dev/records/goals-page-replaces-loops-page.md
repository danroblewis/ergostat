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
