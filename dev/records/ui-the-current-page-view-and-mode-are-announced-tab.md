# ui-the-current-page-view-and-mode-are-announced-tab: The current page, view and mode are announced; tables and controls have names

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q75 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** all pages

**The problem:** Nothing carries aria-current or aria-pressed; tables have th cells in a body row and no caption; the Items h2 names include '▾'; a sort button is named 'Sort by by'; −, + and ⋯ are named by title only; /model rows end in identical 'process, controller, scope' links; the side panel is a div, not a landmark; several targets are under 24 px.

**The change:** aria-current='page' on the nav; aria-pressed on Dynamics/Blocks/Process and on Items' List/Graph/Timeline; <thead>, scope and a caption on each data table; aria-hidden on glyphs; aria-labels 'Zoom out', 'Zoom in', 'More diagram options', 'Sort by author'; row name added to repeated links; side panel as <aside aria-label>; 24 px hit areas on Evidence links, legend links and the Record checkbox.

**User stories it serves:** H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
axe-core on /diagram, /loops, /agents, /items, /record and /model reports no violations of aria-allowed-attr, button-name, link-name, th-has-data-cells or target-size; exactly one nav link has aria-current='page' and exactly one view button has aria-pressed='true'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.
