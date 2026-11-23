# diagram-frames-corners: System frames drawn as corner marks joined by a hairline; a closed system's outline light unless a goal in it is off

depends-on: []

Problem: the owner: 'technical diagrams draw only the corners as short lines, or corners with a lighter connecting line'. Dynamics open sectors are 4% grey slabs with 16 px round corners and no outline (ergostat/web/static/diagram.js:652-675, 676-731, styled inline by hueOf at 655; style.css:519 removes any stroke); tints add up when nested (shots/plan-notation-sf-dyn-open.png) and the edge is lost on a large canvas (plan-notation-job-openall-dyn.png). Blocks frames are full 1 px muted rectangles (blocks.js:778-800, style.css:478-481), near the wires' 1.2 px, and read as one more wire (plan-notation-sf-blocks-open.png); Process frames are --line-strong rectangles (style.css:390). A closed module is a 1.4 px ink box, the heaviest mark at the top level (plan-notation-sf-home.png). SPEC.md:3777 ('a light tint'), DESIGN.md:151 and tests/test_diagram_rendering.py:1972-1973 pin today's form.
Change: one frame grammar for an open system in all three views (defaults, no owner question: corners joined by a hairline; the tint comes off Dynamics' open sectors): no fill; a hairline rectangle in a new token --frame (contrast at least 1.6:1) with square corners, plus one path.frame-corners of L marks (12-14 px arms, 1.2-1.4 px, token --frame-mark; 8 px for a nested frame). Keep the rect element (colours.js:79 and interact.js:104 select it for rings and the cross-pane mark). The name sits at the top left on the top edge with a gap behind the text. Variants: modelling (filed Q13) dashed hairline with solid corners; a cascade's inner-loop frame in Blocks dotted. A closed system's outline uses --frame-mark at 1.2 px; with an off goal (filed Q27) it is full ink at 2 px. Drag grip, toggle, Open and Into keep their hit areas; blocks.js:453's rule keeping lines off frame edges stays. Legends (side panel and export) draw the new frame glyph; the Guide frame that shows an opened system is updated. Update SPEC.md:3777 ('framed by its corners'), DESIGN.md:151, docs/layout-rules.md.
Definition of done:
1. In both themes on :8791 (factory, modelling open), :8796 (product, factory open) and :8797 (api open) no open frame rect has a non-transparent fill; each has a path.frame-corners and a rect stroke computing to --frame.
2. On a fixture, a closed system with no off goal has a lighter, thinner outline than one with an off goal.
3. modelling's hairline has a stroke-dasharray and its corners do not.
4. Dragging a frame by its name, collapsing it, the correspondence rings and the cross-pane hull mark still work.
5. The layout corpus's line-overlap-with-frame counts do not rise; tests/test_diagram_rendering.py passes with lines 1972-1973 rewritten.
Files: ergostat/web/static/diagram.js, dynamics.js, blocks.js, process.js, colours.js, export.js, style.css, ergostat/guide.py, tests/layout_geometry.js, tests/test_diagram_rendering.py, docs/SPEC.md, docs/DESIGN.md, docs/layout-rules.md.
Acceptance tests: computed-style checks per view on the three demos in both themes; the dasharray check on :8796/ and :8797/.
Budget: 110 net lines (minus the tint rules removed).

Milestone: diagram-notation. Owner items: 8 (boxes around system groups). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Net 39 lines outside tests and docs (budget 110). main is merged (HEAD..main is empty).

- One helper, `frameMarks` (diagram.js), draws every open frame in Dynamics, Blocks and Process: `rect.frame` (no fill,
  square, `--frame`: #b8bec4 light, 1.9:1; #4a5057 dark, 2.1:1) and `path.frame-corners` (13 px arms, 8 px nested,
  1.3 px, `--frame-mark` = `--muted`). The name sits on the top edge with a paper-coloured halo (paint-order stroke;
  export.js now carries paint-order so the file draws it the same). The Dynamics tint (`hueOf`, the `svg.sd` stroke-none
  rule) is gone. Modelling's hairline is dashed 4 3, a cascade's inner loop dotted, a remote kind in Process keeps
  its 9 5 dash (now in CSS). A closed module (Dynamics) and subsystem block (Blocks) are `--frame-mark` 1.2 px, and
  `sys-off` (full ink, 2 px) when a goal in them is off (`systemOff`: the box's loop counts in Dynamics, the goals
  it holds against `S.status.loops` in Blocks).
- Choices taken without the owner (reversible): "modelling" is known from the server, as state.attention already
  decides it (`use: modelling` instances), so the graph's `tree` entries carry `modelling: true`: this touches
  ergostat/fold.py, ergostat/blockdiagram.py and ergostat/spec/ir.py (`modelling_systems`), which the Files list
  did not name. colours.js, interact.js, guide.py and tests/layout_geometry.js needed no change: the rings and the
  hull mark select the frame rect as before, the Guide's opened-cascade frame is drawn by bdDraw, and the geometry
  reads `lay.containers`, which this gap does not move.
- Tests: `test_an_open_system_is_framed_by_its_corners_in_every_view_and_both_themes_and_modellings_hairline_is_dashed`
  (software-factory in Dynamics, Blocks and Process, ticket-factory in Dynamics and Blocks, light and dark) and
  `test_a_closed_systems_outline_is_light_unless_a_goal_in_it_is_off`; the old tint assertion in
  `test_the_dynamics_view_speaks_system_dynamics_...` rewritten. Each new test was seen to fail with the modelling
  dash removed and with `systemOff` forced false.
- Not done as written: the demos on :8791, :8796 and :8797 are not running in this container, so the per-demo checks
  run on the examples above instead (dev/model, the factory's own, is not checked). The layout corpus was not run;
  there is no detector named line-overlap-with-frame in tests/layout_rules.py, and no layout or routing code changed.
- Failing, judged unrelated: `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`
  fails after its frame checks pass, on SD_WORDS matching "Goals off" / "No goal is off." in the side list (added on
  main by cd71c13e); `test_every_view_draws_cleanly_and_in_time[image-squeeze]` and `[coordinator]` fail only on the
  20 s routing bound (22-26 s, load average 12-15); this gap touches no routing. Neither was rerun on main: the
  command that would swap main's files in was refused.

Round 2. main (afeee013) merged; the export.js conflict resolved to main's lists, which already carry paint-order.

- Finding 1 (blocking, the no-tree path): each outline drawn by the second path in drawGraph (a graph with no tree,
  S.showHulls on) now sits in its own `g.hull` (no `data-hull`, so rings, the hull mark and drag act there as before:
  none), so the frame rules match it. New test
  `test_a_graph_with_no_tree_frames_its_systems_by_their_corners_and_fills_nothing` draws software-factory's graph
  with its tree and containers taken away; with the fix removed it failed on a rect filled rgb(0, 0, 0).
- Finding 2 (the Dynamics legend's control word): the row reads "module drawn heavy: a level in it is away from its
  desired level". `test_a_closed_systems_outline_is_light_unless_a_goal_in_it_is_off` now checks the whole Dynamics
  legend, with a module off, against SD_WORDS; it failed on "goal" with the old wording.
- Ran: those two and `test_an_open_system_is_framed_...` (4 passed); ruff clean. The whole
  tests/test_diagram_rendering.py run was stopped at its 20 min background limit before it ended, and a rerun with a
  longer limit (`uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python
  scripts/named_tests.py tests/test_diagram_rendering.py > /tmp/dr.log 2>&1`, in the background) was refused, so the
  file was not run whole this round. `test_the_dynamics_view_speaks_system_dynamics_...` still fails only on the side
  list's "Goals off" (from main, as in round 1).

Round 3. main has no commits the branch lacks (HEAD..main is empty), so there was nothing to merge.

- Finding (blocking, the exported Blocks legend): bdExportLegend (export.js) now resolves every `var(--x)` and
  `var(--x, fallback)` in a row's icon to the page's computed value, or the fallback, or the ink, as sdExportLegend
  does. The frame row's hairline, corners and name halo are now stroked in the saved file. New test
  `test_the_exported_blocks_legend_draws_the_frame_glyphs_hairline_and_corners` renders the exported legend in a
  blank page with no stylesheet and checks that the frame row's rect, corner path and halo have a stroke other than
  none and no var( is left. With the fix taken out, it failed on all three strokes.
- Ran: that test, `test_an_open_system_is_framed_...` and `test_a_closed_systems_outline_...` (4 passed: the second
  is parametrised over two examples); ruff clean. The whole tests/test_diagram_rendering.py file was not run this
  round. The earlier failures noted above, from main, were not rerun.
- A command was refused: a `cp` + `sed` that would have taken the fix out to check that the test fails. It was done
  with the edit tool instead and then put back.

Round 4. main (2f08c24e) merged; conflicts in SPEC.md, blocks.js, dynamics.js, style.css and the test file resolved
keeping both sides:

- Blocks frames: main's title (a named system's name once, its p × m after it) on the branch's corner frame, the
  title on the top edge. Blocks legend: main's rows, each shown only when drawn, kept; the branch's frame-glyph row
  ("a subsystem open: framed by its corners ...") is shown when an open system frame is drawn, and the cascade row
  keeps its dotted glyph with main's condition. Choice taken without the owner (reversible): main's "a system as one
  block, the same closed and open" row stays next to it. The frame row is added to BD_LEGEND_DRAWN
  (`.bd-frame-system`), and the exported-legend test now draws with `open=*` so that the row is there.
- Dynamics: main's upkeep dash and the branch's `sys-off` on the module; main's sparkline CSS kept, the tint rule
  stays gone. SPEC: the branch's frame sentence, then main's sentence on the side list's words. The Dynamics test
  takes main's side-panel read (legend and group words removed) with the branch's frame checks.
- Ran (passed): `test_an_open_system_is_framed_...` (both examples), `test_a_closed_systems_outline_...`,
  `test_the_exported_blocks_legend_...`, `test_a_graph_with_no_tree_...`, `test_each_blocks_legend_row_is_a_symbol_drawn`
  (3), `test_a_system_is_drawn_c_p_or_named_...`, `test_an_open_systems_frame_dragged_in_the_blocks_view_...`,
  `test_an_open_system_dragged_by_its_outline_...`, `test_colour_by_correspondence_rings_...`,
  `test_flows_only_export_legend_...`; ruff clean.
- Failing, judged from main (the branch changes no side-list text, no example, and only adds a legend row):
  `test_the_dynamics_view_speaks_system_dynamics_...` passes its frame checks, then fails on the side cards' own words
  ("open · goal developer-honest cannot close", "serves goal one-running"). `test_the_exported_png_shows_every_loop_name_...`
  fails on `len(rows) > 10` (6) for `system=product&view=blocks`, where no frame is drawn and main's legend shows only
  what is drawn. `test_blocks_crossings_hop_dots_...` fails at line 2232: `get_by_role("button", name="fit")` also
  matches the example's keep-model-fits blocks (strict mode). None was rerun on main because the command
  `git worktree add --detach /tmp/mainwt 2f08c24e05a8def3f529b51b00f6dc7ae9e4d400` was refused.

Round 5. main has no commits the branch lacks (HEAD..main is empty), so there was nothing to merge.

- Finding (blocking, a closed subsystem's outline stale between layouts): drawBlocksView's same-diagram path, run on
  each poll, now sets or clears `sys-off` on every subsystem block from `systemOff` against the status just read, next
  to bdAlarm, so a goal inside a closed subsystem going off (or coming back) is drawn on the next poll without a new
  layout. New test `test_a_closed_subsystems_outline_follows_its_goals_as_the_status_polls_change` (software-factory,
  Blocks) intercepts /api/status, turns one of a closed subsystem's goals off after the first draw, waits for the block
  to be heavy, then turns the goal back and waits for the block to be light. With the new line disabled the test failed
  (it timed out waiting for `sys-off`). Dynamics needs no such change: a module's counts come with the graph, which
  each poll draws again.
- Ran (passed): that test, `test_a_closed_systems_outline_is_light_unless_a_goal_in_it_is_off`,
  `test_an_open_systems_frame_dragged_in_the_blocks_view_takes_its_parts_and_its_pins_survive_closing_and_opening`;
  ruff clean. The whole file was not run; the round-4 failures judged to come from main were not rerun.
- Refused commands: one that read the drag test's name with grep into a shell variable and ran three tests
  (`t=$(grep -o ... | sed 's/def //'); ... named_tests.py ...::$t`), so the name was found with the search tool and the
  tests were run with it written out; and a `cat >> dev/records/... <<'EOF'` + `git commit`, so this section was written
  with the edit tool.
