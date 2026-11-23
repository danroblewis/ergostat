# dashboard-panel-controls-on-hover: edit mode adds no bar; a panel shows grab, edit and delete on hover

Owner, 2026-11-23: clicking Edit shifts every panel's content down and adds a header with "a three-dot thing and a left arrow, right arrow, minus, plus, arrows, vertical arrows, the word Edit, and an x". "These should not be visible all the time, they should only be visible when the cursor hovers over it. Also, only the Edit and x buttons are worth including. ... we just need people to be able to: grab and move, edit, and delete."

Change.
- Entering edit mode moves no panel content by a single pixel.
- A panel's controls are only Edit and delete (x), overlaid in the header's corner on hover or keyboard focus, never over the plot area. The title itself is the drag handle.
- Remove the arrow, plus, minus and vertical-size buttons. Resizing stays on the panel's edges and corner. Keyboard move and resize stay available without visible buttons.
- On touch, where there is no hover, the controls appear once a panel is tapped in edit mode.

Definition of done.
1. A browser test measures every panel's plot position before and after entering edit mode: identical.
2. Controls are hidden until hover or focus, and only Edit and delete exist.
3. Drag, resize, keyboard move and delete still work.

## Where it stopped

Built, round 1. Net 0 lines of code outside tests (22 added, 22 removed in dashboard.js and dashboard.css).

- The bar (`.dash-tools` in the flow) and the foot (`.dash-foot`) are gone. Edit and × now sit in a small box laid
  over the top right of the header (absolute, so it moves nothing), hidden (opacity 0, no pointer events) until the
  panel is hovered or something in it has focus. The grip, ←, →, −, + and ↕ are removed. The header (`.panel-head`,
  title included) is the drag handle, as before. Resizing stays on the edges and corner. Enter-to-lift, Alt+arrows
  (move) and Shift+Alt+arrows (resize, tall) stay as they were.
- Something outside the panels also moved them: the page title becomes an input in edit mode (4.3 px taller than the
  h1), and on a phone the buttons edit mode adds (Add panel, Undo, Reset) wrapped onto a new row (34 px). Both are
  fixed in dashboard.css: the h1 and the input share a 32 px height, and below 700 px the actions take one row of their
  own that never wraps and scrolls sideways if crowded. I chose this because it is the most reversible: CSS only, and
  no button is removed.
- Touch: no handler was added. A tap focuses the panel (it has `tabindex`), and `:focus-within` shows its controls.
  Chromium's tap also sets `:hover`, the way mobile browsers do. I wrote a tap-state class first, but no test could
  fail on it (the panel shows its controls without it), so I removed it. Untested: a real iOS or Android browser.
- Touch drag on the title: the title must be held 220 ms first, the same rule a touch drag on the header always had.
  The grip that used to start a drag at once on touch is gone.
- Tests (tests/test_dashboard_page.py): `test_entering_edit_mode_moves_no_panel_content` (done 1, at 1440, 1024 and
  390 px; it compares the page positions of every header, body, canvas, stat and table before, during and after edit
  mode), `test_only_edit_and_remove_show_on_hover_or_focus_and_never_over_the_plot` (done 2; it also opens the editor
  from Edit by keyboard), `test_the_x_removes_the_panel`, `test_on_touch_a_tap_shows_that_panels_controls`, and
  `test_edit_mode_moves_and_resizes_by_mouse` and `test_edit_mode_moves_resizes_and_removes_by_keyboard` (done 3; the
  mouse drag now grabs the title). The old `test_the_tools_never_sit_over_the_plot` is replaced by the done-2 test.
- Seen to fail: done 1 before the header fix (4.3 px at 1440, 34 px at 390); done 2 and the touch test with the
  controls always visible; done 2 with `:focus-within` removed. The touch test still passes with `:focus-within`
  removed, because the tap sets `:hover`.
- Not taken: screenshots. I could not save them here (the command to make /tmp/shots and set DASHBOARD_SHOTS was
  refused), so how it looks has not been seen by eye.
- Build fix: the factory's build ran only the changed test files. Here that was the browser file
  tests/test_dashboard_page.py, which skips without Playwright, so pytest collected nothing and returned rc 5. Added
  tests/test_dashboard_controls.py, which reads done item 2 from the source with no browser: only Edit and × are
  built, and the CSS lays them out of the flow and hides them until hover or focus. main's dashboard.js (←, →, −, +,
  ↕) and dashboard.css (no hover or focus rule) would fail it. The run of the build's whole command under
  suite_watch was refused, so it was not run.
