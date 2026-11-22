# diagram-side-panel-legend-first: The Diagram's default side panel: what waits for you, then the legend of what is drawn; the rest folded with counts

depends-on: []

Problem: with nothing selected the right panel (ergostat/web/static/diagram.js:1332-1406, renderSide) lists 'Not running' and charts, Needs attention (1347), Suggestions (1363-1374, open whenever a goal is off), the charts drawn last (1375), the loop list (dynamics.js:421 sdLoopList or diagram.js:1378-1388, 18-39 rows), The model, and only then 'How to read it' (1405). legendBox (diagram.js:1309-1314) writes localStorage ergostat.legend=closed on first render, so from the second visit the legend is a closed details under about 30 rows: off screen at 1440x900 on :8796 (shots/plan-notation-sf-dyn-open.png) and under 26 attention entries and 35 loop rows on :8797 (plan-notation-big-home.png). blocksLegend (blocks.js:1099) lists every symbol whether drawn or not. The owner: 'Most are useless: make it the explanation of symbols, or at least that first.' The owner's complaint is about broken loops, suggestions, charts and loop lists, not about requests: approving or denying is the one thing a person does here (decision 7, R3), so what waits must not fall below a 30-row legend.
Change: in the default state of every view (Dynamics, Blocks, Process), at every width, the panel is ordered: (1) 'Waiting for you' only when something waits: one line per request, and above 3 one line 'N wait for you' that opens them (filed Q42's group, Q43's header link kept); (2) legendBox(view), titled with the diagram's type and open unless the reader closed it in this browser (it then stays closed); the first-visit 'closed' write goes; the Blocks legend lists only symbols drawn, as sdLegend (dynamics.js:468) does; (3) goals off (the rest of Needs attention, as filed Q42 groups it); (4) Suggestions, the loop list and The model, each a closed details with its count in the summary. The 'charted last' fallback (1375) is removed: charts appear only while parts are chosen. A selected part's panel is unchanged.
Definition of done:
1. On a fixture with no request waiting, in all three views, with fresh localStorage and after a reload, the first heading in #side is 'How to read it' and its details is open.
2. With requests waiting the first heading in #side is 'Waiting for you' and the legend is the second; at 1440x900 both are on screen.
3. Closing the legend survives a reload; reopening too.
4. Suggestions, the loop list and The model are closed details whose summaries carry counts.
5. With nothing selected no chart svg is in #side.
6. Each Blocks legend row's symbol is present in the svg.
Files: ergostat/web/static/diagram.js, dynamics.js (sdLoopList in details), blocks.js (drawn-when filter), process.js (pmSide), tests/test_diagram_rendering.py (line 1970 checks the text after the legend), docs/SPEC.md (side panel paragraph).
Acceptance tests: a browser test per view asserting 1-6 on a served fixture (one with and one without waiting requests).
Budget: 80 net lines.

Milestone: diagram-notation. Owner items: 9. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1: 22 net lines in ergostat/ (budget 80).

- renderSide (diagram.js): with nothing chosen the panel is 'Not running' (a line, not a heading, as before), then
  Waiting for you (the attention entries that carry an answer; above 3, one closed details 'N wait for you'), the
  legend, Needs attention (what is left), then Suggestions, the loop list and The model as closed details whose
  summaries carry their counts. Each is keyed, so a refresh never patches one fold's open state onto another. The
  'charted last' fallback is gone (charts.js redraws the panel when the chosen parts change, as the panel no longer
  always holds the chart box). The legend's summary is 'How to read it · the <diagram type>'; the first-visit
  'closed' write is gone, and only a toggle on the legend in the page writes ergostat.legend.
- blocksLegend lists a row only when the model drawn has that symbol (from S.graph, as sdLegend does).
- Choices made alone (the most reversible): Q42's group and Q43's header link are not on main, so 'Waiting for you'
  is built here from the entries that carry an answer, and there is no header link to keep. For the Process view,
  'the loop list' is its Kinds list (the notes on what was read stay visible under 'The process map').
- inboxAnswer's handlers now read the row as it is on the page. Keying the rows (lesson-5) made the old closures read
  the inputs of a detached tree, so test_inbox_page.py failed (a typed 'how many' was lost); on main the test passed
  only because the row's DOM happened to be rebuilt after the approve.
- Tests (tests/test_diagram_rendering.py): test_the_side_panel_with_nothing_waiting_opens_on_the_legend_and_folds_the_rest
  (DoD 1, 3, 4, 5; per view), test_what_waits_for_you_comes_first_and_the_legend_second_both_on_screen (DoD 2; per
  view), test_more_than_three_waiting_fold_into_one_line_that_opens_them, test_each_blocks_legend_row_is_a_symbol_drawn
  (DoD 6). Seen to fail with: the legend before Waiting for you, the charts fallback back, the toggle not remembered,
  the loop list open, blocksLegend unfiltered. NOT caught: putting the first-visit 'closed' write back. In Chromium
  the legend inserted open fires a toggle that writes 'open' over it, so that write alone does not close the legend
  in this browser. Suggestions need controller hints, which the fixture's model makes none of, so the test adds one
  hint to the page's attention and redraws.
- Changed to follow the new panel: the SD-words test reads the panel but its legend, with the folds opened; the charts
  test expects no chart with nothing chosen; the remote-lines test opens the Kinds fold before reading.
- Whole tests/test_diagram_rendering.py, serially: 201 passed, 9 failed. Fixed: the 2 that followed the panel (above).
  Not this gap: test_every_view_draws_cleanly_and_in_time[coordinator, image-squeeze] (routing 27-29 s over a 20 s
  bound) and test_a_big_tangled_model_lays_out_in_time_and_cleanly (draw 3-4 s over 2.5 s). These are time bounds on
  this container, in layout code not touched. test_every_lines_panel_links_to_the_parts_it_joins[coordinator,
  image-squeeze, ticket-factory] ('link X opened nothing' in the part panel, a different link on a rerun) has a 5 s
  wait, in code not touched. test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page ('Nothing
  waiting.' on the Model page, pages.js, not touched) failed again alone. None could be run on main here (a
  worktree of main was refused); the merge queue must judge them on main.
- Not run: the unit suite, test_page_polling.py, test_page_refresh.py, test_items_page.py, demo_check (no example
  touched). main had nothing new to merge.
- Build step, fix round 1: `build` failed with rc 5, not on this gap's code. The branch changes no Python module, so
  scripts/affected_tests.py chose only tests/test_diagram_rendering.py and tests/test_inbox_page.py; the build step
  has no Playwright, both files skip at import, and pytest returned 5 for no test run. With Playwright here, under the
  watchdog: the four acceptance tests (11 cases) and tests/test_inbox_page.py pass (rc 0); ruff is clean. No code was
  changed. The fix (a build step with Playwright, or affected_tests adding a check that runs when only browser files
  are chosen) is in the factory's scripts, outside this gap (lesson-13).
