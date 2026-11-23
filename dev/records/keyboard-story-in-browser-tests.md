# keyboard-story-in-browser-tests: A keyboard-only run of story H5 is part of the browser tests

depends-on: [diagram-roving-focus-and-arrow-keys]

Problem (R9 piece 6): story H5 (find the goal that is off and read why, without a mouse) failed in the review (shots/story-7-h5-loops-kbd.png), and no test would notice if it failed again after the keyboard work lands.
Change: add tests/test_keyboard_story.py (Playwright, keyboard events only, no mouse or page.click): on a seeded fixture with a planted off goal (not a live demo), from page load: Tab to the diagram; arrow to the system holding the off goal; I to go Into it; arrow to the off goal's gap; Enter to open its evidence; read the panel's first line through the accessibility tree; Escape back; then Tab to the nav and reach the Goals page and its first row's link. The test asserts focus is always visible (document.activeElement has a non-zero box on screen), that each step's accessible name matches the expected kind, and that the whole run takes fewer than 40 key presses. The same run is repeated in Blocks.
Definition of done:
1. The test passes on main once the keyboard gaps (filed Q74, Q75 and diagram-roving-focus-and-arrow-keys) are in, and fails if any of them regresses.
2. It runs with the other browser tests and is skipped under the same condition as tests/test_diagram_rendering.py.
3. The key-press budget is asserted.
Files: tests/test_keyboard_story.py.
Acceptance tests: the test itself.
Budget: 90 lines of test, 0 product code.

Milestone: r9-diagram-without-a-mouse. Owner items: R9 piece 6. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. 0 lines of product code; tests/test_keyboard_story.py is 88 lines (budget 90).

What it does: `test_story_h5_the_off_goal_found_and_read_by_keyboard_alone[view=dynamics|view=blocks]`, keyboard
events only (no mouse, no click; `goto` loads the page). The fixture is test_diagram_rendering.py's
`goal_named(boxed=True)`: charted's record, short-backlog off now, every part inside the closed system desk. Steps:
Tab to the diagram's one stop (desk, its first part); Shift+Arrow to desk only if the stop is elsewhere (it is not,
so on this fixture "arrow to the system" takes 0 presses); I into desk; Dynamics: Right (disturbance arriving →
stock backlog), Down (the connector backlog → short-backlog), Right (the excess, `auxiliary excess backlog`);
Blocks: Right (r short-backlog → `sum Σ short-backlog`); Enter, and the panel's aria snapshot is read: a
`complementary` landmark whose first line is `text: Excess` / `text: summing junction` and that names short-backlog;
Escape back to the gap; Shift+Tab to the nav's `Goals`; Enter (/goals drawn, `aria-current=page` on Goals); Tab to
the first row's `button.name` (short-backlog). After every key: `document.activeElement` is not the body and has a
non-zero box inside the viewport, and its accessible name (aria-label, else text) matches the step. Counted: 36 keys
in Dynamics, 34 in Blocks; `< 40` is asserted. Most of it is Tab through the header and toolbar into the diagram and
Shift+Tab back to the nav. The Tab and Shift+Tab legs check the name only of where they stop (each press is
still checked for a visible focus); every other key is one press that must land on its expected name.

Choices made alone (each the more reversible one):
- "Its first row's link" on /goals is a `button.name` (goalRow), not an `<a>`; the test asserts that button.
- "Read the panel's first line": the first line inside the landmark of Playwright's `aria_snapshot()` (the
  accessibility tree); the landmark itself is checked, as Q75's.
- Done item 2, only half met: the file imports the browser fixture and helpers from tests/test_diagram_rendering.py,
  so it skips exactly where that file does (its `importorskip("playwright.sync_api")` at import, then no Chromium).
  But the queue's and the daily run's browser command (dev/factory.toml `[suites] browser`, and `browser_paths`)
  name the four browser files, as does CLAUDE.md's browser command; none is in this gap's Files list, and changing
  the factory's own gate from inside a gap is not this gap's to do. So it does not yet run with them: the file must
  be added to `browser` and `browser_paths` in dev/factory.toml (and to CLAUDE.md's command) by whoever owns the
  factory's config. Until then the merge queue never runs it (the unit suite has no Playwright, so it skips there).

Seen to fail with the code broken (lesson 9), each reverted after: the roving stop off (every part tabindex 0 and
focusin not resetting the others): Dynamics' focus off screen, Blocks 45 keys; Blocks' Right along the return path
in place of the forward one: Blocks fails; a line's Right/Left ends swapped: Dynamics fails; I not handled: both
time out; Enter not handled: both fail; Escape not giving the focus back: both fail; no aria-current on the nav
(Q75): both time out; #detail a div, not an aside (Q75): both fail at the landmark. A first try at the roving break
(tabindex 0 alone) passed, because keys.js's focusin handler moves the stop back on the first focus; the roving
stop still works then, so that is not a regression of it.

Run here: tests/test_keyboard_story.py under suite_watch with Playwright (2 passed, rc 0, none skipped, about 4 s),
ruff (clean). Not run: the unit suite, the four browser files, demo_check (no example touched). Main is in the
branch (it is the base; nothing to merge).
