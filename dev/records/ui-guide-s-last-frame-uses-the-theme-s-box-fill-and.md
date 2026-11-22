# ui-guide-s-last-frame-uses-the-theme-s-box-fill-and: Guide's last frame uses the theme's box fill, and says it is loading

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q06 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /guide?frame=12

**The problem:** In light mode the system dynamics thumbnail draws boxes as solid black with unreadable text; arriving by the arrow, the frame is blank for 1 to 2 s with no text.

**The change:** Draw the thumbnail with the page's theme tokens (the same fill as the live diagram). Until both thumbnails have rendered show 'Drawing your system…' on the stage.

**User stories it serves:** A3

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At /guide?frame=12 in light mode every system-box rect in the left thumbnail has a computed fill equal to the live diagram's box fill, and its text contrast is at least 4.5:1; 200 ms after pressing → from frame 12 the stage contains visible text.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built.

- **Cause of the black boxes.** The box itself already drew in the theme's tokens (`svg.sd .sd-module`, white in
  light mode, as live). Over each box's outline, `colours.js` puts correspondence rings (`rect.corr-halo`,
  `rect.corr-ring`, clones of the outline). The only rule that hides them (`display: none; fill: none`) was scoped to
  `svg.canvas`, and the Guide draws into `svg.g-canvas`, so they showed with SVG's default black fill under the text.
  The fix (style.css) applies that same rule to `svg.g-canvas`. The Guide has no correspondence toggle, so its rings
  are never shown. Both thumbnails get the fix, since both are `g-canvas`.
- **Loading text.** guide.js: on the last frame (`yours`), a muted "Drawing your system…" line goes on the stage until
  both thumbnails' drawings have settled, then it is removed.
- **Reading of the acceptance (the more reversible choice).** URLs are 0-based, so `/guide?frame=12` is the last
  frame (shown as 13 / 13), and → from it goes nowhere. "200 ms after pressing → from frame 12" is read as arriving
  at that frame by the arrow: from `?frame=11` (shown 12 / 13). The test slows `/api/graph` by 1.5 s in the page, so
  the blank window is always there to be seen, whatever the machine's speed.
- **The test.** `tests/test_diagram_rendering.py::test_the_guides_last_frame_draws_its_boxes_as_the_live_diagram_does_and_says_it_is_drawing`
  (software-factory, light mode). It counts every drawn rect of each `g.node.k-system` in the left thumbnail, but not
  the transparent Into/Open button rects. Each must equal the live dynamics view's box fill, with the title's contrast
  on it at least 4.5:1. It was seen to fail both ways: before the CSS fix, two rects were `rgb(0, 0, 0)` against the
  live `rgb(255, 255, 255)`; with the loading line disabled, the stage text was `''`.
- **Ran:** the new test and `test_the_guide_draws_every_frame_live_and_in_a_snapshot` (both pass, with Playwright,
  under the watchdog); tests/test_guide.py (6 passed); ruff clean. Not run here: the unit suite and the four browser
  files, which the factory and the merge queue run.
- **Size:** 5 net lines outside tests (guide.js +2, style.css +1 rule line), within 60.
