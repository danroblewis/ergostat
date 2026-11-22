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

## Where it stopped

Built, round 1; 18 net lines outside tests (64 added, 46 removed under `ergostat/web/static/`).

Decisions taken alone (each the reversible one):
- **axe-core itself is not run.** It is not in the repository or the environment, and the session reaches no network.
  The acceptance test (`tests/test_items_page.py::test_the_page_view_and_controls_are_named`, nine pages: /diagram in
  Dynamics, Blocks and Process, /loops, /agents, /items, /items?kind=hypothesis, /record, /model) checks the five
  rules in the page the way these pages use them: aria-allowed-attr for aria-pressed, aria-sort, aria-checked; button-name and
  link-name (stricter than axe: a title alone, or a glyph with no letter, is no name); th-has-data-cells (a header
  row out of a thead, an unscoped column header, a column header over no data cell, a data table with no caption);
  target-size for the named 24 px targets (Evidence links, the Items graph's legend keys, the Record checkbox), not
  every target on the page. Vendoring axe-core and running it in this test is a later step if wanted.
- aria-sort moved from the sort button (where aria-allowed-attr forbids it) to its th; the existing sort test reads it there.
- 'Sort by author' is said for a field named `by` (examples' `show: [..., by]`); any other field is 'Sort by FIELD'.
- The Items page's seg helper sets aria-pressed on all its toggles (Show, and in Graph/Timeline, Group and Rows):
  the test counts pressed buttons in the View/Show group only. Graph and Timeline were not opened by the test.
- The diagram legends hold no links; the 24 px "legend links" taken as the Items graph's legend keys (button.rg-key).
- The Items group headings already had their ▸/▾ aria-hidden on main; the menu buttons' CSS ▾ is now `content: "▾" / ""`.
- Two tests in test_diagram_rendering.py used the old names ('+', 'process') and now use 'Zoom in' and 'quality-held process'.

Tests seen to fail when the code they guard is broken (lesson-9): with the thead, 'Zoom out' and aria-sort-on-th
undone, all nine cases failed on the matching rule; with aria-current and aria-pressed removed, all nine failed.

Tests run: tests/test_items_page.py (31 passed), tests/test_agents_page.py (4 passed), tests/test_diagram_rendering.py
in full (194 passed, 6 failed; the two failures caused by the renamed controls fixed and passing on a rerun). Left failing, not touched by this branch:
- test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page (line 3305, 'Nothing waiting.' on
  /model's proposal list): a past review recorded it failing alone; still failing on the rerun.
- test_every_view_draws_cleanly_and_in_time[coordinator] and [image-squeeze] (routing 39 s and 34 s against 20 s),
  test_a_big_tangled_model_lays_out_in_time_and_cleanly (4.2 s against 2.5 s): layout and routing time bounds in a
  50-minute serial run; this branch changes no layout code. Not compared with main here.
- Not run: tests/test_page_polling.py, tests/test_page_refresh.py, the unit suite (left to the factory and queue).

Found, not fixed (outside the gap): opening /model writes a new ergostat.model-change item to the record (seen as
ergostat.model-change/8da394d2 on the image-squeeze site), so a test after it on the same site sees four model
changes, not three; the acceptance test is placed last in its file for that reason.

Build step after round 1 (rc 5, "2 skipped"): not a fault in the branch's code. The branch changes only
`ergostat/web/static/` (JS and CSS) and two browser test files, so `scripts/affected_tests.py` selects only
tests/test_diagram_rendering.py and tests/test_items_page.py; `[suites] build` runs them without Playwright, both
skip at import, and pytest returns 5 (no tests ran). No change to this gap's code can make that command pass: it
would take changing the build step or affected_tests.py (outside this gap, lesson 13) or adding an unrelated unit
test only to be selected (a test that guards nothing). Left as is; the fix belongs to the factory (run the build
step's browser files with Playwright, or treat a selection of only browser files as collection-only). The browser
files were run with Playwright in round 1 (results above).
