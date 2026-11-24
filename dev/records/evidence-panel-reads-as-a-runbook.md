# evidence-panel-reads-as-a-runbook: A goal's evidence opens with its four lines, then the charts, then parts and prose; the remedy comes from its suggestion

depends-on: [goal-row-one-renderer]

Problem (R7 piece 7): the evidence panel is the best thing in the product (y with r, u and e on one time axis, crossings, decisions) and every reviewer said to keep it, but it answers an SRE's questions in a modeller's order and words: parts and prose first, 'Not worked out: it has no one process', the remedy elsewhere under Suggestions (shots/story-2-c1-evidence.png, story-2-c5-evidence.png, sreb-job-loop-panel.png).
Change: reorder openLoop's panel (ergostat/web/static/details.js:140 onward, control.js): (1) four lines first, each one sentence: what is wanted and where it is now (the goal's word through goalWord, bound written per filed Q23, the distance in the one phrase of one-phrase-for-how-far-off when landed); how long off against how long it usually takes (filed Q29); what acts on it and whether it was commanded, ran and moved (filed Q28's line); what to expect (the forecast sentence when present); (2) the remedy line: the suggestion for this goal from the snapshot's hints (ergostat/state.py:524-589), shown only when it has a verdict (filed Q80's rule), with its Evidence link; (3) the charts; (4) parts, the control-loop table (filed Q69) and the prose, with 'Not worked out: it has no one process' reworded to what a reader can do. The lines are built by functions the quick fixes own, in whatever order they land: this gap only orders and adds the remedy and expectation lines.
Definition of done:
1. On a fixture an off goal's panel has, before any chart, four one-sentence lines and (when a suggestion with a verdict exists) one remedy line.
2. The charts follow; parts and prose come last.
3. The remedy text equals the Suggestions entry for that goal; the first line's word equals /api/loops' word.
4. No sentence in the first screen of the panel contains 'Not worked out'.
5. At 390 px the four lines fit without horizontal scroll.
Files: ergostat/web/static/details.js, control.js, style.css, tests/test_diagram_rendering.py.
Acceptance tests: a browser test of the panel's order and the remedy line on the fixture.
Budget: 90 net lines.

Milestone: r7-evidence-is-a-runbook. Owner items: R7 piece 7 (pieces 1-6 are filed Q26, Q28-Q31, Q33, Q34, Q36). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1 (+31 net lines outside tests, budget 90):

- `openLoopNow` (details.js) now draws, after its title: four `p.runbook-line`s in a `div.runbook`, then the remedy line(s),
  then the scope (y, u, e and "How it is doing"), then the description, the dl of rows, the parts table, breaking,
  interventions, Ahead, the control box (the control-loop table), Cannot close, the ladder suggestions, crossings,
  decisions; the "About" definitions stay last (showDetail).
- The lines (`runbookLines`): (1) the word (`goalWord`, as a status span) with the measure, its bound (`goalBound`, the
  server's `bound_words`) and value, and `off_by_words`; (2) how long off (`goalOffFor`) against the usual time back
  (`back_in`), or that there is none yet; (3) the Q28 actor lines (each still a `span.actor-line` with the same text),
  joined in one sentence; (4) "Ahead: ..." set by `goalAhead` from the forecast sentence when it comes, else what is
  known (being worked out, no estimate, could not be read, a snapshot makes none). No quick-fix function for Q23/Q29
  was on main, so these sentences are put together here from the helpers goalrow.js already has (`goalBound`,
  `goalOffFor`). When those fixes land, their functions should take over lines 1-2. The Ahead section stays as it
  was (tests/test_forecast_panel.py reads it), so the forecast sentence appears twice: in line 4 and under Ahead.
- The remedy (`remedyLines`): the goal's `about: loop` hints. Those exist only once there is a verdict (state.py
  sets `diagnosis_in` and makes no hint before then). Each is drawn as "Remedy: " followed by the page's own
  Suggestions entry for that goal, word for word, because Dynamics words its entries itself ("goal NAME ..."), with
  the hint's own text when the page has no Suggestions list (/loops), then an "Evidence" link that scrolls to the
  scope. Ladder hints stay below as "Suggestion:". My choice, and easy to undo: the Evidence link points at the
  panel's own charts, since the panel is already the goal's evidence.
- control.js: the scope's "Not worked out: it has no one process." now reads "Read it by its time off and its crossings
  (below): <why>." and "Not worked out yet: too little record…" now reads "Its numbers come once the loop has more
  record: …". tests/test_agents_page.py now reads the loop's suggestion at `#detail p.remedy` (it moved there).

Acceptance test: tests/test_diagram_rendering.py::test_a_goals_evidence_opens_with_its_four_lines_and_its_remedy_then_the_charts_then_parts_and_prose
(Dynamics and Blocks at 1500 px, Dynamics at 390 px, on goal_named's off goal). Passes. I broke the code three
times to check the test fails: the remedy dropped (fails on the remedy), the charts put before the lines (fails on
the order), and the old "Not worked out" wording put back (fails on the 390 px pass). That pass answers
/api/loop-control with a no-one-process analysis, because the fixture never reaches that sentence by itself. Item
4 is checked over the whole panel's text, which is wider than its first screen.

Not done, or not proven:
- Failing after this change. None of the failing paths is code the branch changes. I could not run them on main's
  code: `git worktree add -q /tmp/ergo-main main` and `git checkout main -- <the three files>` were refused in this
  session.
  - tests/test_agents_page.py::test_each_row_says_how_it_is_engaged_and_which_goal_it_serves fails twice out of two.
    The Agent panel reads "Loading…": the test waits for the `h2` that `panelLoading` draws at once, then reads the
    panel before the answer (openAgent is unchanged).
  - tests/test_diagram_rendering.py::test_a_suggestion_appears_when_it_has_a_verdict times out waiting for the
    side list's "Needs attention" entry (diagram.js) before any panel opens.
  - test_every_part_opens_its_panel_when_clicked_even_mid_redraw (the panel for stock:pending-changes) and
    test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words (waiting on /api/part/flow)
    fail in the part and flow panels (openNodeNow, openEdge, dynamics.js), which are unchanged.
- Not run by me: the whole unit suite and the four browser files (the factory runs them).

Round 2:

- Merged main (59600738): the one conflict in details.js was resolved by keeping main's title ("Goal", "Goal, open loop",
  `whatIs("goal")`) and adding the branch's runbook lines and remedy before the scope.
- The review's finding (line 3 says "Nothing that acts for it ran in this window" when no actor is listed): fixed.
  `unlisted` in details.js now says only what is known. With no valves it says "Nothing is declared to act on it: no
  block drives its stock". With valves but no listed agent it says "No agent that acts for it is recorded", then that
  its valves opened N times in this window (`openings_total`), that they did not open, or that whether they opened is
  not known. The acceptance test now adds a fixture goal that no block acts on (`small-backlog`) and checks its third
  line, and it checks that the off goal's third line lists its block (`worker: commanded…`). I put the old wording
  back and the test failed on that third line, then passed again with the fix. The "valves but no listed agent" case
  is not covered by a fixture: a blocks model always gives each valve its block as agent (spec/legacy.py), so only an
  older valve-format model reaches it.
- Run: the acceptance test (passes), tests/test_forecast_panel.py (passes), and ruff (clean). tests/test_agents_page.py:
  13 pass, and test_each_row_says_how_it_is_engaged_and_which_goal_it_serves fails as in round 1 (the Agent panel
  still reads "Loading…"; openAgentNow is unchanged by the branch). The whole tests/test_diagram_rendering.py was
  stopped at its 20-minute limit about 30% through, with about 25 failures, roughly one test in four. It did not
  name them, so I cannot say which failed or why. Not run: the unit suite and the other browser files.

Round 3:

- The review's finding (line 3 says "Nothing is declared to act on it: no block drives its stock" whenever the loop has
  no valve, though a block may set the goal's auxiliary directly, or move its stock for another goal): fixed.
  - ergostat/web/server.py (outside the Files list, the reversible choice the finding itself names): /api/loops/NAME
    now also gives the controller's `through`, and its actors also take the blocks on that path when the path ends at
    the goal's own auxiliary (the block that sets it directly, spec/legacy.py), so such a block is listed with its
    commanded, ran and moved counts like any other actor.
  - `unlisted` (details.js), when the loop has no valve: with a path, "It is acted on through A → B; what each did is
    not counted here" (reached only if none of its blocks could be listed); with no path, "No block acts for it:
    nothing that reads it or M moves M, directly or through what it commands" (the loop finder's own rule, ir.py
    `_loop`: actuators are what the blocks reading the goal or its measure reach); with `through` missing, "What acts
    on it is not known". The words "its stock" are gone. The fixture's `small-backlog` now reads that sentence: worker
    does move backlog, but for short-backlog, and reads neither.
  - The acceptance test adds a fixture goal `low-throttle` on an auxiliary `throttle` that block `damper` (in:
    goal.low-throttle.error, out: auxiliary.throttle, no goal: key) sets, and checks its third line starts "damper:
    commanded". With the server's new actor source removed, the test failed on that line (it read "It is acted on the
    long way, through damper → throttle; …", the wording since made neutral), then passed again.
- Run: the acceptance test and tests/test_forecast_panel.py (pass), ruff (clean). tests/test_agents_page.py: 13 pass,
  test_each_row_says_how_it_is_engaged_and_which_goal_it_serves fails as in rounds 1-2 (the Agent panel reads
  "Loading…"; openAgentNow is not touched by the branch). Not run: the unit suite and the four browser files whole.
