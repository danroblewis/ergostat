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
