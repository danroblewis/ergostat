# attention-names-goals-as-goals: Attention entries and suggestions name a goal as 'goal NAME', with the name as a field, not parsed from words

depends-on: []

Problem: every attention entry about a goal is written 'what': f'loop {name}' (ergostat/state.py:632-655) and every suggestion starts 'loop NAME was off N% of the time...' (state.py:524, 554, 560, 563, 589); the CLI summary says '3 loops: 2 holding, 1 open' (ergostat/cli/running.py:360-362). Four places find the goal by parsing those words: ergostat/dynamics.py:450-462, ergostat/cli/status.py:113 (a['what'] == f'loop {n}'), ergostat/web/static/diagram.js:1372 (/^loop (\S+)/.exec(a.says) gives the Evidence link) and review.js:58 (finds the panel heading by `loop ${goal}`). Renaming the words alone would silently break the Evidence links and the CLI's 'items about it': the same class of bug as filed Q46's find-and-replace. It is ranked directly with the rename so the header never says 'goals off' over a list that says 'loop X was off'.
Change: each attention entry and hint about a goal carries goal: NAME; its what reads 'goal NAME' and its text 'goal NAME was off...', built from the name as a token. The four parsers read the field: dynamics.attention takes a['goal'] (or a['controller'] for a controller hint); status.py matches a.get('goal') == n; diagram.js uses a.goal for Evidence; review.js finds the goal's panel by a data attribute. running.py reads '3 goals: 2 holding, 1 open'. level, says and order stay; words for controllers, sensors and agents and the event types loop.off/loop.holding do not change. Filed Q62's word changes in dynamics.attention become no-ops.
Definition of done:
1. On a fixture with an off goal, /api/status attention entries for it have what == 'goal NAME' and goal == NAME; no what starts with 'loop '.
2. On /diagram in Dynamics and Blocks each suggestion about a goal has an Evidence link that opens that goal's panel.
3. `ergostat status` on a project with an off goal that has open items prints 'goal NAME:' then '· items about it'; --system S still filters.
4. The full suite passes.
Files: ergostat/state.py, ergostat/dynamics.py, ergostat/cli/status.py, ergostat/cli/running.py, ergostat/web/static/diagram.js, review.js, docs/DESIGN.md:124,130, tests/test_goal_per.py:121-122,194, tests/test_observer.py:110,291, tests/test_item_about.py:282,306,335, tests/test_dynamics_view.py:149-153, tests/test_graph_cli_web.py:140.
Acceptance tests: the updated tests; a new unit test that a goal's attention entry carries goal; a browser check of the Evidence link.
Budget: 40 net lines of code, 20 of tests.

Milestone: goals-not-loops. Owner items: Decision: 'goal' instead of 'loop' for what is held or off (R11 piece 1). From the owner's list and the design review of 2026-11-22.
