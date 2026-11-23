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
- Build step, fix round 2: rc 5 again, for the same reason (every file chosen skips without Playwright). Added
  tests/test_legend_memory.py, which needs no browser. It reads the static scripts and fails if ergostat.legend is
  written anywhere but the legend's toggle handler, so it now catches the first-visit 'closed' write coming back,
  which the browser tests could not. Seen to fail with that write put back in legendBox; passes without it. The
  build step now picks it, so it runs at least one test. ruff is clean. No page code changed.
- Round 2, merge of main (720426bd): main landed Q42's groups (Waiting for you, Goals off, Model housekeeping, each
  entry led by its state or kind word). The conflict in renderSide is resolved as this gap's order over main's
  groups: Waiting for you (main's rule for what waits: an answer that is not a held request, or a.waiting) only when
  something waits, above 3 folded into 'N wait for you'; then the legend; then Goals off and Model housekeeping as
  main draws them; then Suggestions, the loops and The model, closed. The rows stay keyed (lesson-5). The panel's
  own 'Needs attention' heading and its 6-entry cap are gone, replaced by main's groups. Q43's header link is still
  not on main. style.css keeps both sides' rules. SPEC's side-panel paragraph names the two groups.
- Round 2, after the merge: the SD-words test (test_the_dynamics_view_speaks_system_dynamics_...) failed on Q42's
  own words, 'Goals off' and 'No goal is off.', which are the same in every view. On main this test reads the panel
  before 'How to read it', and there main's groups come before the legend, so by reading it fails on main too (main
  could not be run here). Choice made alone, the most reversible: the test now skips Q42's group headings and empty
  lines (h3.att-head, .att > .none) and still checks every entry and fold. Whether the Dynamics view should say
  'Goals off' at all is the owner's call, about Q42's wording, not this gap's.
- Whole tests/test_diagram_rendering.py after the merge, serially under the watchdog: 209 passed, 5 failed. Fixed: the
  SD-words test (above; passes alone now). Not this gap, as in round 1: test_every_view_draws_cleanly_and_in_time
  [coordinator, image-squeeze] (routing 41-44 s over 20 s), test_a_big_tangled_model_lays_out_in_time_and_cleanly
  (draw 3.1 s over 2.5 s), and test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page ('Nothing
  waiting.' missing on the Model page, pages.js; failed again alone). Also passing: the four acceptance tests, main's
  test_needs_attention_is_three_headed_groups_in_a_fixed_order, tests/test_inbox_page.py, tests/test_legend_memory.py.
  ruff is clean. Not run: the unit suite and the other browser files.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 13:29).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 668, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 13:29).

Its runs failed past their attempts (a dead letter):
- attempt 15: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 16: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 17: nack a switch drains the runs under way (run/drain.json): taken again after it
- attempt 18: nack the run ended with gap/diagram-side-panel-legend-first still parked

## Where it stopped

Continued, round 1 (2026-11-23): the merge of main (2a97eafb) finished, and what the merge broke fixed.

- Conflicts resolved. diagram.js: main's inboxAnswer (the row found from the button, focus to the reply) and main's
  list rows (inboxBody, goalButton, `key: a.what`, data-row) and hold-still (hold(att, cls)) kept; this gap's order
  kept over them (Waiting for you only when something waits, then the legend, then Goals off, Model housekeeping, the
  folds). list() takes main's class plus a key. SPEC: main's hold-still sentences kept in the inbox paragraph, this
  gap's side-panel paragraph after it.
- What the merge broke: main added a `const DIAGRAM_TYPE` (the caption) beside this branch's, so diagram.js failed to
  load ("Identifier 'DIAGRAM_TYPE' has already been declared") and no page drew. The legend's is now LEGEND_TYPE.
  The fold of more than 3 was `details.waiting`, a class main now uses for its "N updates waiting" note (absolutely
  placed); it is `details.waiting-fold`.
- Merging the two rules: main's "a list the reader is in holds still" and this gap's fold of more than 3 clashed. A
  4th entry arriving while the pointer or focus was in a list of 3 moved the held list into a closed fold, hidden
  under the reader. Now, while the list is held, it stays folded or unfolded as it was, and it folds once the reader
  leaves. New test: tests/test_inbox_page.py::test_a_list_the_reader_is_in_is_not_folded_away_when_a_fourth_comes.
  Seen to fail with the guard taken out.
- Main's inbox tests changed to follow the fold. Their `three` fixture has 4 waiting, and in the keyboard test
  alarms push the list past 3, so the reader now opens "N wait for you" first (helper unfold()). The side-panel
  test reads only the panel's own headings (`:scope > h3, :scope > details > summary`), as main's entries now carry
  folds of their own ("the command").
- Run, under the watchdog: tests/test_inbox_page.py whole, 8 passed. The four acceptance tests (11 cases) passed,
  as did the SD-words test and tests/test_legend_memory.py. ruff is clean.
- Fails, not this gap: test_needs_attention_is_three_headed_groups_in_a_fixed_order (main's test). It waits for
  /loops? off/ in #running, but main's header (util.js:398, not touched by this branch) now says "1 goal off, not
  running". The panel's three groups are right ('Waiting for you 1', 'Goals off 2', 'Model housekeeping 2'). The
  header's wording and count differ from the test's, on main's side.
- Not run: the unit suite, the rest of tests/test_diagram_rendering.py and the other browser files. A first try at
  the acceptance tests before the DIAGRAM_TYPE fix hung on the broken page and was stopped at its time limit.

## Where it stopped

Continued, round 2 (2026-11-23): the merge of main (7cb97857) finished.

- Conflicts resolved. Main made the side panel's loop rows `<button>`s (everything clickable reached by keyboard);
  this branch put the loop lists in closed folds. Both kept: in diagram.js (Blocks/Control loops) and dynamics.js
  (sdLoopList) the rows are buttons appended inside the `details.loops` fold. No other change.
- Run, under the watchdog: the four acceptance tests (7 cases in the three named files run together, plus
  test_each_blocks_legend_row_is_a_symbol_drawn), tests/test_legend_memory.py and tests/test_inbox_page.py whole
  (12 passed together); the SD-words test, test_a_module_counts_its_loops_in_the_side_list_... and
  tests/test_dynamics_view.py pass. ruff is clean.
- Fails, not this gap: test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard (main's new
  test) at line 2281, the focus never on '#detail h2' after Enter on a stock. Traced with a focusout listener (taken
  out again): openNodeSD (dynamics.js:680) calls showDetail, which takes S.keyHead and focuses its h2, then at once
  panelLoading (dynamics.js:706) calls showDetail again, which replaces that h2, so the focus falls to the body. Both
  are main's code (dynamics.js openNodeSD, details.js showDetail, keys.js), not touched by this branch, so this
  should fail on main too (main could not be run here). The fix (keyHead kept until the last showDetail of one
  press, or no first showDetail before panelLoading) is in its own gap.
- Fails, not this gap, as in round 1: test_needs_attention_is_three_headed_groups_in_a_fixed_order waits for
  /loops? off/ in #running, and main's header (util.js:398) says "N goals off".
- Not run: the unit suite, the whole of tests/test_diagram_rendering.py (a background run of it was refused here) and
  the other browser files.

## Where it stopped

Continued, round 3 (2026-11-23): the merge of main (ead497d1) finished.

- Conflicts resolved. diagram.js: main's waitsOnYou (util.js, the header's count) is the rule for what waits. Main's
  `id="waiting" tabindex="-1"` (where the header's "N wait for you" link goes, Q43) is on this branch's "Waiting for
  you" heading, which is drawn only when something waits (the header's link is hidden when nothing does). Main's
  dropped chart fallback agrees with this branch's. tests/test_inbox_page.py: both sides' tests kept. Main's
  `aria-label^="Why"` (now "Why deny the push") is used in this branch's unfold() test too.
- What the merge broke: main's new test_a_typed_reason_stays_with_its_entry_when_one_above_is_answered has 4 waiting,
  so this branch folds them. With unfold() added (as main's other tests here have), it failed: the reason typed was
  lost when the top request was answered and 4 became 3. Keyed rows match only among siblings, so the rows moving
  out of the fold were made again. Now, when the fold is made or undone, the list on the page is patched and moved
  into its new place (renderSide, `moved`), so what is typed stays with its row. Seen to fail without this; passes
  with it.
- Choice made alone (the most reversible): following the header's link with the list folded scrolls to and focuses
  the heading, as on main; it does not open "N wait for you" (util.js toWaiting, main's, not touched).
- Run, under the watchdog: tests/test_inbox_page.py whole (10 passed); the four acceptance tests (7 + 1 cases);
  tests/test_legend_memory.py; the SD-words test; tests/test_dynamics_view.py (15 passed). ruff is clean.
- Fails, not this gap, as in rounds 1 and 2: test_needs_attention_is_three_headed_groups_in_a_fixed_order (waits
  for /loops? off/ in #running; main's header says "N goals off").
- Not run: the unit suite, the whole of tests/test_diagram_rendering.py and the other browser files.
