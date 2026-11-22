# ui-each-polarity-sign-sits-on-its-own-arrow-and-eve: Each polarity sign sits on its own arrow, and every top-level link has one

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q25 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram Dynamics, links between systems

**The problem:** Signs are stacked at the receiving edge where 7 to 15 links converge; the nearest sign is the wrong one (missing-ops → filed-features read backwards); deployed → shipped has no sign; driven-by links are solid though the README says dashed.

**The change:** Place each sign beside its own arrowhead, offset along that link, at 13 px or more, never within 10 px of another sign. Give every drawn link a sign or a '?'. Draw driven-by links dashed.

**User stories it serves:** B6, G3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8796/ and :8793/ no two polarity glyphs' boxes overlap or lie within 10 px; each glyph's nearest link path is the link it belongs to (data attribute); every link has a sign glyph.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. Nothing left inside the definition.

- What changed: `sdPlaceSigns` (ergostat/web/static/dynamics.js) places every connector's sign after all are drawn,
  back along its own curve 13 px or more from the tip (at most 160 px back), beside it (±5/±9 px) or on it, where no other link
  line is as near, its box 10 px or more from every other sign's (the most hemmed-in first; one sign in the way moved
  aside where that makes room). Each glyph carries `data-edge`. An unknown polarity shows `?` (was nothing). A
  connector whose model link is declared with driven-by gets `drivenBy` (ergostat/dynamics.py) and is drawn dashed.
  The legend says `?` and dashed.
- Outside `ergostat/web/`: the `drivenBy` flag is set in ergostat/dynamics.py (5 lines). The page can't tell a
  driven-by link from others without it, so this was the smallest way.
- The ports: which demos run on :8796 and :8793 isn't written anywhere in the tree. software-factory's names
  (missing-ops, filed-features, deployed → shipped) match the problem statement, so :8796 is taken to be
  software-factory. Not knowing :8793, the test was made wider instead of guessing: it checks the first page of every
  example in `examples/` (21, software-factory among them, with at least 5 links and driven-by ones), on free ports.
- Test: tests/test_diagram_rendering.py::test_each_polarity_sign_sits_on_its_own_link_apart_from_the_others_and_every_link_has_one
  (21 cases, all pass). SD_CHECK in the existing dynamics test now expects `?` for an unknown polarity.
  Seen to fail under each of three breaks: placement switched off (signs 3 px apart and nearest another link);
  `?` left out ("sign of …: " for an example's links); the dashed rule removed ("driven-by, drawn solid").
- Run here: the new test; test_the_dynamics_view_draws_only_system_dynamics_symbols_each_loop_marked_each_sign_shown;
  test_the_background_hides_the_side_panel_and_a_part_dragged_stays_pinned; the guide test; the flows-only export
  legend test; the remote dashed-line test; tests/test_dynamics_view.py; ruff. All pass.
- Not passing here, and not caused by this change: test_a_big_tangled_model_lays_out_in_time_and_cleanly fails its
  2500 ms layout budget in this container with sign placement switched off as well (3538 ms; with it, 3888 ms). The
  budget times `layoutGraph` only, not the draw. Sign placement itself measured 151 ms for 302 links in that model's
  open=* view, once per geometry (memoized on the paths' `d`).
- Not run: the unit suite and the four browser files in full (the merge queue runs them).
- Size: 60 net lines outside tests/docs/dev (88 added, 28 removed), at the budget.
