# module-box-sparklines: a closed module shows its headline measures as small line graphs

Owner, 2026-11-23: "I saw a neat feature briefly on the staging environment that gave the system dynamics modules line graphs ... it was cool", and "they were in the module boxes, probably sparklines."

Boxes once drew sparklines; on 2026-11-16 they moved into the module's panel (`moduleCharts` in `ergostat/web/static/charts.js`). Bring them back on closed modules only.

Change.
- In the Dynamics view, a closed module's box shows sparklines for at most three headline measures, chosen from the system's `show:`, else its goals' measures. Each has its name and current value, in the box's existing rows, with no new panel.
- Stocks, flows and auxiliaries stay as they are: no sparklines on them, so the stock-and-flow notation stays textbook.
- The line is a behavior over time on the page's time window, with a stated scale: it does not imply that two sparklines share a y axis. A missing or stale reading shows as a gap, never as a flat line or a zero.
- The diagram's structure draws first. Sparklines fill in afterwards from one batched request to the measurement store, refresh on the page's interval, and never move the layout or change a box's size.
- Clicking a module still opens its panel with the full charts.
- At a zoom where a sparkline would be unreadable it is not drawn.

Definition of done.
1. A closed module shows up to three sparklines with its current values; an open module, stock or flow shows none.
2. A browser test: positions of every box are identical before and after the sparklines load.
3. One batched request serves all visible modules, and it does not read the event log.
4. A series with a gap in its readings draws a gap.
5. tests/test_diagram_rendering.py passes on every example and view, in light and dark.

Files: ergostat/web/static/dynamics.js, ergostat/web/static/charts.js, tests.

## Where it stopped

Round 1, 2026-11-23. Built; done items 1 to 4 have acceptance tests that pass. Done item 5 does not hold: 34 tests in
tests/test_diagram_rendering.py fail on this branch, and every one I could check also fails with this branch's page code
switched off (details below).

What is built (net 171 lines outside tests, docs and dev; the budget is 600):
- `dynamics.js`: `sdSparks` runs after each draw of the main canvas. For each closed module it takes the first three of
  its `charted` measures (its `show:`, else its goals'). It skips a remote module, since its readings are not in this
  store, and ergostat's own upkeep box. All of them go in one request,
  `api("series", {refs, points: 44, measured: 1})`. A box has nothing until that answer comes. The answer is
  cached by window (`since`, `at`), drawn again from the cache on every redraw, and asked again once 2.5 s (the page's
  interval) have passed. A newer ask or a change of window makes a late answer be ignored (by sequence number). A failed
  answer clears the cache, so no lines show, and it is asked again on the next interval.
  `sdSparkRow` draws each measure as its name, its value now (from `charted`), a 44×12 line and its scale
  ("lo–hi"). These go in the widest free stretch of one of the box's existing rows: the description's second line
  (y 56) and each port row (from `sysTop`, every `SYS_ROW`). The space is measured from the real text there (`getBBox`,
  with a width estimate for a port name that Flows only hides). A measure that does not fit, even without its unit, is
  left out, so a narrow box may show fewer than three. Nothing is added to the layout, and no box changes size.
- `charts.js`: `sparkPath` breaks the line at any bucket that has no reading or holds a non-finite number. A reading
  alone between gaps is a dot.
- `diagram.js` (two lines, outside the Files list): `drawGraph` calls `sdSparks` in the Dynamics view, and `applyView`
  calls `sdSparksZoomed`. That redraws the lines, or takes them away, when the zoom crosses the readable size (the line
  under 7 px high on the screen, i.e. zoom < 0.58).
- `style.css` (outside the Files list): the line, its name, value and scale, in the Dynamics ink tokens.
- `series.py` and `server.py` (outside the Files list): `GET /api/series?measured=1`, answered before the snapshot is
  taken, from the measurement store alone (`series.measured`). Stocks and auxiliaries come from `level`; a flow comes
  from its sensors' readings only. A flow with no sensor is all None and says "not measured". It never reads events,
  so it never shows valve openings or item moves. At most 60 parts (`MEASURED_REFS`), at most 1,000 points. The
  existing `series` answer reads the event log for flows and needs the snapshot, so done item 3 required this route.
  Choosing the extra route was my call (nobody to ask). It is reversible: drop the route and `series.measured`, and the
  page falls back to drawing no lines.
- SPEC §4a, *Drawn as parts*: says what a module box draws and how. The `dynamics.py` and `moduleCharts` comments no
  longer say a box draws no measures.

Tests (each run alone, through scripts/named_tests.py; the browser ones with Playwright, under suite_watch):
- tests/test_module_sparklines.py (3, pass). The measured answer, with the event log replaced by an object that fails
  on any use and `state.snapshot` made to raise. Gaps are None where nothing was read, and after the readings stop. A
  flow no sensor reads is all None. The ceiling on parts holds.
- tests/test_diagram_rendering.py::test_a_closed_module_draws_three_sparklines_after_its_structure_without_moving_a_box
  [light, dark] (pass). Done items 1 to 4: the first answer is held while every box's place is measured, and the places
  are identical after it. One ask carries both boxes' refs. Exactly the first three of four `show:` measures are drawn,
  inside the box, with name, value and scale. Backlog's line has two subpaths across its 20-minute hole. None is drawn
  at zoom 0.3. A failed answer takes the lines away and the next answer brings them back. The page asks again on its
  interval. A click on a line opens the module's panel. An open module draws none, and with everything open none is
  drawn at all.
- ...::test_an_examples_closed_modules_find_room_for_their_measures_and_nothing_read_is_no_line (pass). In
  image-squeeze, served unrun, every closed module with a `show:` draws at least one measure inside its box, each with
  no line and the scale "no readings".
- Seen to fail (lesson 9): drawing across gaps fails the subpath check; ignoring the zoom fails "drawn too small to
  read"; shifting the rows 30 px fails "a box moved or changed its size".
- tests/test_page_polling.py: 22 passed, rc 0. tests/test_series.py, tests/test_parity.py, tests/test_spec_schema.py:
  pass. ruff: clean.

What is left:
- tests/test_diagram_rendering.py, the whole file run serially: 34 failed, 279 passed (57 min, rc 1). I reran these
  with this branch's two `diagram.js` hooks switched off, which leaves only the server route, and only `measured=1`
  reaches it. They failed the same way:
  - `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip` on 21 examples: the loop marker's
    `<title>` "Drawn alike here with …" (dynamics.js:579, from 1208bfab on main).
  - `test_every_view_draws_cleanly_and_in_time[autoscaler, the-job, ticket-factory]`: layout-rule ceilings
    (satellite-far 6 > 0 and 15 > 14, valve-orientation-mismatch 3 > 2). The layout does not depend on this branch.
  - `test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout`: the dragged parts do not move.
  - `test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard`: the focus is not on the panel
    heading.
  - `test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode`: 6 legend lines
    where it wants more than 10.
  - `test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words`: it times out waiting for a
    response.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: the Model page does not say
    "Nothing waiting.".
  - `test_needs_attention_is_three_headed_groups_in_a_fixed_order`: a timeout at line 5944.
  - `test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`: the "fit"
    role name matches 5 elements (Blocks view).
  - `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`: flaky, a different stock each time. With the hooks
    off it passed once and failed once; with them on it passed once and failed twice. Its view (`open=*`) has no
    closed module, so no sparkline is asked for or drawn.
  - `test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False]` failed in the long run
    and passed when run alone, with the hooks on and with them off.
  - Not rerun alone: `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`. It is the
    Blocks view, which this branch does not draw in. Run alone it timed out at its first draw (240 s).
  I could not run them on main itself: `git checkout main -- ergostat` was refused. The factory's rerun on clean main
  should confirm. Under lesson 13 they are reported here, not fixed in this gap.
- How many of the other examples' closed modules show three lines, rather than one or two, is not measured. Only
  image-squeeze's "at least one each" is tested. A scratch Playwright probe to measure it was refused:
  `uv run --with playwright==1.63.0 python /tmp/sp/probe.py image-squeeze /tmp/sp/is.png`.
- No screenshot was taken, so how readable the lines are at the 7 px threshold is a judgement, not checked by eye.
- The static snapshot (SNAP) draws no lines, because the measured answer is not in a snapshot.
- main was not merged in again: the clone has no remote, and local main is the base this branch was made from.

Round 2, 2026-11-23. The only finding was the merge conflict with main in `ergostat/web/server.py`. It is resolved
in f84bb81f, keeping both sides. The branch's `series?measured=1` route still answers before any snapshot is taken.
After it, main's line `snap = pinned if pinned is not None else live.snapshot(...)` (the dashboards' shared
snapshot) replaces the branch's plain `live.snapshot(...)`. No other code changed in this round.
After the merge: ruff clean; tests/test_module_sparklines.py 3 passed; tests/test_series.py,
tests/test_parity.py and tests/test_spec_schema.py 62 passed. The two sparkline acceptance tests in
tests/test_diagram_rendering.py, run with Playwright under suite_watch, gave 3 passed, rc 0. tests/test_page_polling.py (Playwright, suite_watch): 22 passed, rc 0. The whole of
tests/test_diagram_rendering.py was not run again in this round (57 min last time). Done item 5 stands as round 1
left it: the failures listed above, which also failed with this branch's page hooks off. These failures
are for the factory's rerun on clean main to confirm.

Round 3, 2026-11-23. The finding: tests/test_graph_cli_web.py::test_the_side_panels_charts_say_being_worked_out_never_a_bare_ellipsis
failed alone, and so did the batch of 3 that held it. This branch caused it. The test refuses any quoted text in
charts.js that is or ends in "…". My `sparkPath` comment had ``lo``…``hi``, which the test reads as a quoted "…".
The comment now says "from ``lo`` to ``hi``". No code changed. No other "…" is added anywhere in the branch's diff
under ergostat/ (checked with a grep of `git diff main`).
Tests run after the fix: tests/test_graph_cli_web.py 54 passed. tests/test_module_sparklines.py 3 passed. These four
browser tests (Playwright, under suite_watch) gave 4 passed, rc 0: test_no_panel_shows_a_leftover_ellipsis (the
browser half of the same check) and the two sparkline acceptance tests (3 cases). ruff is clean. main is already merged
in (the local main is an ancestor of HEAD). The whole of tests/test_diagram_rendering.py was not run again. Done item 5
stands as rounds 1 and 2 left it.

Round 4, 2026-11-23. The finding (blocking): past `MEASURED_REFS` (60) the server dropped refs without saying so, and
the page drew every ref it asked for and got no answer to as "no readings" ("nothing read over the window"). So past
20 closed modules, boxes with readings in the store said they had none (lessons 3 and 8). It was the only finding, and
it is fixed. I kept the single batched request (done item 3) and did not ask in chunks:
- `series.measured` now names the refs past the ceiling in its answer's `cut` (in the order asked). It still reads at
  most 60, so the ceiling holds (lesson 4).
- `sdSparks` now treats any ref it asked for and got no answer to (cut, or unknown to the server) as not known, and
  draws nothing for it. "No readings" now shows only for a part the server answered with no readings in the window.
  The upshot: on a diagram with more than 20 closed modules, the later boxes show fewer lines, or none. Chunked asks
  would draw them all, but done item 3 asks for one request. Choosing this was my call (nobody to ask). It is
  reversible: the page could ask a second time for `cut`.
- SPEC §4a says both.
Tests: tests/test_module_sparklines.py::test_parts_past_the_ceiling_are_named_as_cut_never_answered_as_unread (70
measured stocks, every one read: the first 60 answered with their readings, the last 10 in `cut`). The ceiling test
now also checks `cut`. tests/test_diagram_rendering.py::test_a_measure_the_answer_cut_past_its_ceiling_draws_nothing_never_no_readings
(the answer rewritten as the server's would be past the ceiling, with archive's `stock.filed` cut: archive draws
nothing, while reception's three draw as before). Seen to fail (lesson 9): with the page's old null prefill, the
browser test fails on archive's "filed 149 no readings". With `cut` always [], both unit tests fail.
Run: tests/test_module_sparklines.py, tests/test_series.py and tests/test_spec_schema.py, 49 passed.
tests/test_parity.py and tests/test_graph_cli_web.py, 71 passed. The three sparkline browser tests plus the new one
(Playwright, under suite_watch), 4 passed, rc 0. ruff is clean. The whole of tests/test_diagram_rendering.py was not
run again. Done item 5 stands as rounds 1 to 3 left it.
