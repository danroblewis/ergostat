# headline-one-function-everywhere: The page and the CLI never count goals themselves: header, switcher, side list, Goals page and `ergostat status` print the server's one count

depends-on: [goal-state-says-its-system-and-upkeep]

Problem (R6 piece 8): the header counts goals with status off in the browser (ergostat/web/static/util.js:364); the side list's group and the Goals page each count their own rows; `ergostat status` prints its own summary (cli/running.py:360-362). The numbers disagree at the same moment (shots/story-1-b3-loops.png, pm-job-loops-4s.png). goal-state-says-its-system-and-upkeep makes the one server function (state.goals_off) and uses it in /api/status and projects._row; this gap is the cleanup that makes every other surface print it and nothing else.
Change: the loops answer's summary and the CLI's status and projects lines call state.goals_off. The page never counts: the header (with filed Q14's layout), the switcher, the side list's group heading and the Goals page's heading print the numbers they were given. A test fails when page code filters goals by status to make a count. Later fields of the count (in_grace, from queue-goal-grace-in-words) are added to the one function and reach every surface through it.
Definition of done:
1. On a fixture with a system goal, an upkeep goal and an open goal off, at one moment the header, the switcher entry (seen from another project), the side list group's count and the Goals page heading show the same numbers as /api/status goals_off.
2. `ergostat status` and `ergostat projects` print the same numbers.
3. grep finds no `status === 'off'` count in util.js, pages.js or diagram.js outside row styling.
4. A snapshot file shows the counts it was saved with.
Files: ergostat/web/server.py (loops summary), ergostat/cli/status.py, ergostat/cli/running.py, ergostat/web/static/util.js, pages.js, diagram.js, tests/test_graph_cli_web.py, a browser test.
Acceptance tests: the agreement test on the fixture; the grep test.
Budget: 50 net lines.

Milestone: r6-off-tells-the-truth. Owner items: R6 piece 8 (with the owner's decision on the headline). From the owner's list and the design review of 2026-11-22.
