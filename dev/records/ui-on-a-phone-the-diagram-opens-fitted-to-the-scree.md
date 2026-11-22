# ui-on-a-phone-the-diagram-opens-fitted-to-the-scree: On a phone the diagram opens fitted to the screen

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q73 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram at 390 px

**The problem:** At 390 px the canvas is blank on the-job (neither box in view), shows part of one box on software-factory, and opens mid-drawing inside a system.

**The change:** On load and on every change of view at narrow width, fit the drawing to the canvas (down to the minimum text size, then centred on the first off part with a direction hint).

**User stories it serves:** A1, H4

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
At 390x844 on :8792/ and :8796/ at least one whole system box is inside the canvas viewport at load; on :8796 ?system=product the stock 'users' or a direction hint is visible.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: about 26 net lines (diagram.js, style.css). Choices made alone, each easy to undo:
- "Narrow" is style.css's own phone layout, `(max-width: 700px)` (where the toolbars move off the canvas), not the
  canvas's width, so a desktop split pane under 700 px keeps the desktop fit.
- "The minimum text size" is zoom 0.7 (11px text at 7.7px), the zoom the desktop first view already shows whole.
- "The first part" is the first system box in the graph's order, else the first stock, else the first node; the view
  is centred on it but kept from showing space beyond the drawing's edges.
- The direction hint is the existing "More beyond the edge" (no longer hidden on a phone), with arrows for the ways
  the rest lies (←↑→↓), at every width.
- The acceptance's ":8792/" and ":8796/" are the-job and software-factory served by the test at /diagram (the bare
  "/" on a phone goes to /loops by design, main.js). Unrun, the-job draws at 320x312 and fits whole even before this
  change, so that half of the test cannot fail here; the software-factory ?system=product half failed before the
  change (k 0.8, panned from the left, no hint), and fails with the centring disabled or the hint hidden again.

Tests: tests/test_diagram_rendering.py::test_on_a_phone_the_diagram_opens_with_a_whole_system_box_in_view, 2
passed. The whole tests/test_diagram_rendering.py (serial, watchdogged): 6 failed, 196 passed, none skipped. The 6 run
at 1400-1600 px, where the narrow fit never runs: the routing and drawing time bounds (every_view[coordinator],
[image-squeeze], a_big_tangled_model) and the 'Nothing waiting.' equation test, all reported on other branches before;
the blocks-drag test passed when run again; every_lines_panel_links[ticket-factory] failed again, on different links
each run (its 5 s wait for a panel), and the run on main's page code to compare was refused here, so the queue
should confirm it on main.

Build step, after round 1: `build` ended rc 5 because the only test file it picked was the browser file, which skips
whole without Playwright, so nothing ran. The page code did not change. Added a non-browser test,
tests/test_style_tokens.py::test_on_a_phone_the_direction_hint_is_not_hidden (no narrow-layout rule hides .panhint),
so the build step runs a real check of the style change: 6 passed in that file; it fails with `.panhint` put back in
the phone layout's `display: none` rule. ruff clean.
