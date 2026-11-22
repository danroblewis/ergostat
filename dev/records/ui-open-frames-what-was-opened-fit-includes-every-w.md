# ui-open-frames-what-was-opened-fit-includes-every-w: Open frames what was opened, Fit includes every wire, and the edge hint says which way

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q71 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Open, Into, Fit)

**The problem:** After Open the opened system lands half off-screen under a large empty area; Fit still leaves wires and labels beyond the right edge; 'More beyond the edge' does not say where; the floating toolbar covers labels.

**The change:** After Open or Into, pan and zoom so the opened system's bounds are in view (at no less than the minimum text size). Fit uses the bounds of every node, wire and label. The hint reads 'more to the right / below' and is clickable to pan there. Keep the toolbar off the drawing's bounds.

**User stories it serves:** H2, A5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797 after Open on api, api's bounding box is wholly inside the canvas viewport or a hint naming a direction is shown; after Fit on :8791 ?view=blocks&system=modelling every path's and text's bounding box is inside the viewport and no hint is shown.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. 34 net lines in `ergostat/web/static/diagram.js` (+46, -12). Main has no commits past the branch's base, so there was nothing to merge.

- **Fit and the first view** now frame what is drawn (`drawnBox`: the `#viewport` group's `getBBox()`, so every part, line and label), not only the layout's box. They leave 60px clear above and below for the two floating toolbars.
- **The edge hint** is now a button. It names each way the rest lies ("More to the right and below") and, when clicked, pans most of a screen that way, no further than the edge.
- **After Open** (`showSystem`), the system stays where its box was if all of it is in view. Otherwise it is moved the least needed to bring it in, zooming out if needed but to no less than 0.8, the zoom the first view already treats as legible. If it is still too big, its top left goes to the top left of the view and the hint names the way to the rest.
- **After Into**, the view is fitted to the system drawn alone, as before. It now uses the drawn bounds.

Choices made without asking (each is easy to undo):
- The old rule was that an opened system stays exactly where its box was. Now it holds only when the system fits on screen. `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` was changed to match: a move is allowed only if the outline then lies wholly inside the canvas, and the pinned box's check takes off the pan.
- The demos on :8797 (api) and :8791 (modelling) are not in this clone. The tests use `examples/software-factory` instead: its top-level systems opened from their boxes, and `system=modelling` in Blocks and Dynamics.

Tests:
- New: `test_fit_shows_every_line_and_label_and_no_edge_hint[blocks|dynamics]` and `test_open_frames_the_system_opened_or_says_which_way_the_rest_lies`.
- I broke the code four times and the tests failed each time:
  - The drawn bounds replaced by the layout's box: Fit[blocks] failed (a text beyond the right edge, with no hint shown).
  - `showSystem` disabled: the Open test failed (factory's outline reached past the right edge).
  - No room left for the bottom toolbar: both Fit tests failed.
  - The hint text put back to "More beyond the edge": the Open test failed.
- `tests/test_diagram_rendering.py` run whole, serially, under the watchdog: 201 passed, 2 failed (rc 1).
  - `test_every_view_draws_cleanly_and_in_time[image-squeeze]` failed in the whole-file run and passed when run alone just after. I did not see its failure message: the summary line is all the run printed. It is not yet shown to be unrelated.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` fails again when run alone, at tests/test_diagram_rendering.py:3403. The /model page does not say "Nothing waiting." after a calibration is accepted. That is the Model page's list of proposals, which this change does not touch. I could not confirm it fails on main: putting main's diagram.js back to rerun the test was refused.
- Not run here: the other three browser files and the unit suite.
