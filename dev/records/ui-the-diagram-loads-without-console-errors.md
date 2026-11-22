# ui-the-diagram-loads-without-console-errors: The diagram loads without console errors

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q81 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views, all demos)

**The problem:** Every diagram load logs 'xOffset value … in ShapeConnectionPin constructor greater than shape width'; some log 'ELK failed … reading Sg', after which a fallback layout may explain some overlaps.

**The change:** Clamp the pin offset to the shape width (an off-by-one at the right edge). Find the input that makes ELK throw and fix it or report the fallback on the page ('simplified layout').

**User stories it serves:** G3, G5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
Loading /diagram in Dynamics, Blocks and Process on all six demos, and Into each system, produces no console error or warning from the layout.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 1). Nobody could be asked, so these are the choices made, each the most reversible:

- **The pin.** It wasn't an off-by-one. libavoid works a shape's width out again from its corners, and in floating
  point that can come out a hair under `w`, so an absolute pin at `x = w` (a system box's east port in Dynamics, a
  block's east port in Blocks, which was already clamped to `c.width`) lay past it. Fixed in one place,
  `avoidCore` (`ergostat/web/static/avoid.js`): absolute pins are handed to libavoid as a share of the shape's own size,
  clamped to [0, 1]. The pin specs (`avoidSpec`, `bdAvoidSpec`) are unchanged.
- **ELK.** The input that throws ('reading Sg'): MULTI_EDGE wrapping of a chain that loops back through an anchor
  block (first-loop's and talking-scripts' `modelling` system, Dynamics, drawn alone; cutting any edge of that loop
  stops the throw). SINGLE_EDGE wrapping lays the same graph out. So the input is fixed rather than reported:
  `runLayoutWith` (`layouts.js`) tries the same rows cut at single lines before it drops wrapping. The old fallback
  and its `console.warn` stay for anything that still fails. No 'simplified layout' text was added to the page: no
  demo reaches the fallback now, and a page notice is easy to add later if one does.
- **"All six demos".** Nothing names six, so the test covers every example in `examples/` (21) through `page_of`: a
  superset.
- **Tests** (tests/test_diagram_rendering.py): `test_every_view_loads_with_no_console_error_or_warning` (the
  acceptance: Dynamics, Blocks and Process, whole and `system=` each system, every example, page and worker console)
  and `test_a_port_on_a_parts_right_edge_is_never_past_it_for_libavoid` (opens the rounding window: every part moved
  under a pixel to where `(x + w) - x < w`, routed again, with a guard that the window opened). Each was seen to fail
  with its fix undone: the old pins log 'xOffset value (240.031) … greater than shape width (240.031)'; the old
  catch logs 'ELK failed … reading Sg' on first-loop `view=dynamics&system=modelling`.
- **Size:** 12 net lines in `ergostat/` (avoid.js +7/−3, layouts.js +8/−1), within the 60.
- **The whole of tests/test_diagram_rendering.py** (serial, under the watchdog, in this container): 221 passed and
  6 failed. Five of them also fail with both JS changes undone by hand, so they don't come from this branch:
  `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]` (`open=*` routing 27–33 s against
  the 20 s bound, with or without the change), `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`
  (`stock:bugs-live`), `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`,
  `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` ('Nothing waiting.' on /model).
  The sixth, `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it`,
  failed only in the long run and passed when run alone, both on this branch and with the changes undone. Under
  lesson 13 they are reported here, not fixed. The other three browser files were not run (nothing they cover changed).
  `main` is already in the branch: the clone has no newer main.
