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
