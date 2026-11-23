# dynamics-off-status-on-the-part: Dynamics: a goal's gap prints the goal's one word, and an off goal's gap and loop marker take the off colour, never the accent

depends-on: [dynamics-every-goal-drawn, goal-row-one-renderer]

Problem (R5 piece 8): in Dynamics nothing on the drawing says which goal is off; the reader matches names from the side list to parts. Once every goal's gap is drawn (dynamics-every-goal-drawn) the gap is the place to say it. The accent already means selection and trace (docs/DESIGN.md's colour rules, settled in diagram-line-tones), so an off goal must not use it, or a traced loop and an off goal would be the same colour.
Change: the gap auxiliary of a goal that is not holding prints the goal's `word` through goalWord (goal-row-one-renderer; no mapping of status in dynamics.js): 'off' with how far ('off by 36', the one phrase of one-phrase-for-how-far-off when present) in --bad, the marker of the goal's balancing loop in --bad too; 'no feedback' for an open goal; the neutral words (approaching, in grace) in the neutral token when they exist; holding goals stay in ink with no word. Not colour alone: the word is always printed. The gap -> flow link stays full ink. Values update with the values poll without a re-layout. The legend and the Guide frame explain the mark.
Definition of done:
1. On a fixture with off and holding goals, open=*: each off goal's gap node has the 'off' text and computes to --bad; holding goals' gaps do not.
2. The word on each gap equals that goal's `word` in /api/loops.
3. A lit (selected) loop's stroke and an off gap's stroke compute to different colours, in both themes.
4. A goal turning off between polls is marked without a re-layout (layout counter unchanged).
Files: ergostat/web/static/dynamics.js, style.css, ergostat/guide.py, tests/test_diagram_rendering.py.
Acceptance tests: a browser test for 1-4 on the fixture.
Budget: 40 net lines.

Milestone: r5-dynamics-tells-the-story. Owner items: R5 piece 8 (first half). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Round 1: built. 22 net lines outside tests, docs and dev (budget 40).

What changed:
- `dynamics.js`: `sdGapWord(n)` gives a gap its goal's word through `goalWord` over the status poll's loops
  (`S.status.loops`, the same snapshot entries `/api/loops` answers), and, off, the one phrase of how far
  (`off_by_words`: `off by 7 tickets`; a phrase without "off", such as `28 short of 180`, reads `off, 28 short of 180`).
  Nothing in dynamics.js maps a status. The word is a tspan after the gap's value on the value's own line
  (`7 · off by 7 tickets`), so no line is added or taken away, the layout signature never changes, and a goal going
  off between polls is marked on the next redraw with no new layout. An off gap's group has `gap-off`; each loop
  marker whose loops include a balancing loop through an off gap has `goal-off`. The legend has a row for the mark.
- `style.css`: the off word (bold), the off gap's outline and the off marker's arc, head and letter in `--bad`; other
  words in `--sd-muted`. The off gap's outline rule outranks a lit loop's `.node.in-loop .hit`, so a traced loop never
  paints an off gap in the accent. The gap → flow link is not touched (ink).
- `guide.py`: the "between" frame says a goal not holding says so on its gap, 'off by 36' in red, its marker red too.
- docs/DESIGN.md (a bullet) and SPEC §12a's Drawn paragraph say the same.

Decisions taken alone (the most reversible option each):
- The word is read from the header's status poll (every 5 s, awaited before the first draw), not added to the
  dynamics graph's gap node: dynamics.py and graph.py are not in this gap's Files. Before the status has come no word
  is printed; once it has, a goal missing from it reads `unknown` (goalWord's own rule), never holding.
- "The neutral words (approaching, in grace)" do not exist yet; the words that do and are not off (`stale`,
  `unknown`) are printed in the neutral token, as Blocks prints them. So in a demo that has not run, every gap now
  reads `· unknown`.
- `open`: a gap already marked `→ no feedback` (dynamics-every-goal-drawn) keeps that line as its word and gets no
  second one; an open goal whose gap lacks the mark gets `· no feedback`.
- A loop marker the reader chose (or hovers) still takes the accent over `--bad`: that is selection, the reader's act.
  An off gap's outline stays `--bad` even inside a lit loop.

Tests: tests/test_diagram_rendering.py::test_a_goals_gap_in_dynamics_says_its_word_and_an_off_one_is_red_never_the_accent
(a YAML fixture of three goals, each closing a signed balancing loop: off, holding, never read) covers done items 1-4,
the neutral word, and the legend and Guide text. It was seen to fail with each of these broken, one at a time: the off
outline in the accent (item 1), the outline rule weaker than the lit loop's (item 3, light theme), the marker's class
dropped (item 1's marker), the word frozen at the first status (item 4 times out), and a word counted as a label line
so it lays out again (item 4: layouts 2 against 1).

Run here, one at a time under the watchdog: the new test (passes);
test_every_product_goal_is_drawn_in_product_and_its_stock_panel_names_the_same,
test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks,
test_the_guide_draws_every_frame_live_and_in_a_snapshot, test_flows_only_export_legend_lists_only_what_is_shown,
test_a_loop_marker_lights_its_loop_and_opens_its_panel (all pass); tests/test_guide.py (8 passed); ruff (clean).
test_every_view_draws_cleanly_and_in_time over every example: 20 passed, 3 failed. The 3 are the ones the
dynamics-every-goal-drawn record names as failing on main, with the same counts (autoscaler satellite-far 10 > 0,
the-job valve-orientation-mismatch 3 > 2, ticket-factory satellite-far 15 > 14). No size fixture moved.

Failing, not caused by this branch (each is text this diff does not touch):
- test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known: the side list carries the
  server's attention lines "open · goal … cannot close: …" (state.py:771) and "serves goal", which its word check refuses.
- test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode: in Blocks,
  `blocksLegend()` has 6 rows where the test wants more than 10.
Neither was run on main here: a worktree of main (`git worktree add /tmp/mainwt main -f`) was refused as a command.
Not run here: the unit suite and the four browser files whole (the factory runs them); demo_check (no example touched).
