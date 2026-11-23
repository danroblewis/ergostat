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

## Where it stopped

Round 1: built. Code net +6 lines (41 in, 35 out under ergostat/). Tests net about +80 lines.

Overrun reason: the code is within its 40 lines; the tests run past their 20 lines because the definition asks for checks no existing test covered: a browser test that clicks Evidence in both Dynamics and Blocks and checks that review.js scrolls the controller panel to the goal by data-goal (about 40 lines), a /api/status unit test for the goal field on entries and hints, a projects-summary test (no test read that table before), and a --system check for `ergostat status`.

What was built:
- state.attention: every entry about a goal is {what: 'goal NAME', goal: NAME}. ladder_hints: the off-share and anti-windup hints carry goal and read 'goal NAME was off...' / 'goal UP keeps feeding ... while goal DOWN is off'. Hints about a goal become attention entries {what: 'goal NAME', goal: NAME}; the ladder (rung) hints stay 'controller NAME'. The event type loop.holding@ in the anti-windup text stays.
- dynamics.attention takes a['goal'] and no longer parses what. A goal's what stays 'goal NAME', and words() keeps 'goal NAME' for the snapshot's goal names but still turns the bare word 'goal' into 'desired level'. The old rewrite of 'controller X' to 'loop X' (Q62) is gone, so a ladder hint's what goes through words() like any other text and reads 'decision X'. This is how I read "takes a['goal'] (or a['controller'] for a controller hint)" and "Q62's word changes become no-ops". It was a judgement call and is easy to undo.
- status.py: 'items about it' joins the entry with a.get('goal') == n (problems only, as before; hints never matched). The --system filter is unchanged: it still reads the name after the first word of what.
- diagram.js: Evidence uses a.goal. control.js: the two goal-section h3s carry data-goal, and review.js finds the heading by dataset.goal (exact match; the old includes() also matched 'loop a' inside 'loop ab').
- running.py: the code has no '3 loops: 2 holding, 1 open' line. The closest is the `ergostat projects` table, so I changed that: the column is GOALS and a row reads '3 goals: 2 holding, 1 off: x' or 'no goals'. The off list is kept and the held count is now shown next to it; the projects data cannot tell open from off, so 'off' stays as the word.
- docs/DESIGN.md §5 updated.

Not changed: tests/test_graph_cli_web.py:140 ('loop disk-under-80' from `ergostat system host`) still passes unchanged, because that text comes from show.py's loop line (the `loop` topic), not from attention. The CLI's loop topic words, controller/sensor/agent words and the loop.off/loop.holding event types are outside this gap. docs/cli-rounds.md is a historical log and is left alone.

Break checks (lesson 9): diagram.js back on the /^loop (\S+)/ regex fails the browser test (no Evidence link); review.js matching the wrong goal fails it (no scroll); status.py back on what == 'loop n' fails 2 tests in tests/test_item_about.py.

Round 2: merged main (bf6dbebf). Conflicts resolved, keeping both sides. state.py keeps main's off_by_words with the branch's goal field. diagram.js's Evidence keeps main's goalButton/showGoal and reads a.goal. test_dynamics_view keeps main's 'off by 4' and the branch's goal checks. test_diagram_rendering keeps both new tests. Main had added three readers of the old words, and the merge left them on 'loop NAME', where they would silently stop matching: state.attention's state/modelling tag (what == f'loop {name}', now a.get('goal') == name), diagram.js's goal button in the attention list (/^loop (\S+)$/ on a.what, now a.goal), and main's tests that look up 'loop NAME' (test_inbox, test_off_by_words, test_graph_cli_web:401, test_diagram_rendering:2980, 4994, 4996), now 'goal NAME' or the goal field.

Two browser tests from main fail here for reasons outside this gap (lesson 13); neither is fixed in the branch:
- test_diagram_rendering.py::test_needs_attention_is_three_headed_groups_in_a_fixed_order waits for the header to match /loops? off/, but main's util.js, which this branch leaves unchanged, prints 'N goals off'. It also asserts the header count equals the list's 2, while the header counts only the system's goals ('1 goal off'; modelling's are counted apart as upkeep). Main's own util.js and test disagree. With both checks patched temporarily (and reverted), the rest of the test passed, including the branch's 'off · goal …' lines.
- test_diagram_rendering.py::test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False] is a race in main's openLoop and in the test. TITLED matches the 'Loading…' panel, the test calls closeDetail 12 ms later, and openLoop's pending answer then reopens the panel, which hides .side, so the Suggestions button is not visible. This was traced with timed calls: loading 806 ms, close 818 ms, show 824 ms. With a temporary 2 s wait before closeDetail (reverted), both parameters passed, including the branch's hint button. The fix belongs in openLoop (drop an answer whose panel was closed while it loaded), in its own gap.
I could not confirm either failure on a checkout of main: `git worktree add -q --detach /tmp/mainwt main` was refused.
