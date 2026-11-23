# diagram-roving-focus-and-arrow-keys: The diagram is one tab stop with roving focus; arrow keys follow pipes, connectors and signals

depends-on: []

Problem (R9 piece 4): the diagram is the interface by the owner's decision, and filed Q74 makes its parts focusable. On big that is hundreds of tab stops before the side panel, and Tab order says nothing about structure (shots/a11y-8791-home.png, a11y-8797-stock-click.png). Story H5 failed.
Change: the SVG is one tab stop (roving tabindex: one part has tabindex 0, the rest -1; the last focused part is remembered per view). Arrow keys move along the structure: in Dynamics Right/Left follow the pipe downstream/upstream from a stock or valve, Up/Down step through the connectors into and out of the focused part (announcing the other end and the link's sign); in Blocks Right/Left follow the signal forward/back and Down takes the return path. On a closed box with goal rows, Down enters its rows. Enter opens the part's panel and moves focus into it; Escape returns focus to the part; I goes Into a focused system and Escape (or Backspace) back out; Home goes to the first part of the first chain. A visible focus ring uses the accent token (selection, by the colour rules). Works on the build Q74 lands (same focusable elements).
Definition of done:
1. On :8791 Tab reaches the diagram once and leaves it with the next Tab.
2. From a focused stock, Right moves focus to its outflow valve and again to the next stock, in Dynamics; in Blocks Right from a junction reaches C, then the actuator, then P.
3. Enter opens the panel with focus inside; Escape returns to the same part.
4. I on a system goes Into it and Escape returns with focus on that system.
5. The focus ring has at least 3:1 contrast in both themes.
Files: ergostat/web/static/interact.js, diagram.js, dynamics.js, blocks.js, style.css, tests/test_diagram_rendering.py.
Acceptance tests: keyboard-only browser tests for 1-4 on :8791 in both views.
Budget: 160 net lines.

Milestone: r9-diagram-without-a-mouse. Owner items: R9 piece 4 (pieces 1-3 are filed Q74, Q75, Q77). From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built, round 1. Net 116 lines outside tests and docs (keys.js +111, details.js +1, diagram.js +1, style.css +3),
inside the 160 budget.

Where the code went, and the choices made alone (each the more reversible one):
- Q74 landed as `ergostat/web/static/keys.js` (the focusable parts, Enter, Escape back to the part), which the
  Files list does not name since it was written before Q74 landed. The roving stop and the walk are in keys.js beside
  it, not spread over interact.js, dynamics.js and blocks.js; diagram.js gets one line (`S.here`, the system drawn,
  so Escape knows where out is). The Blocks return-path test copies blocks.js's own (sensor, collector, bus, or
  `feedback`).
- details.js (not in the Files list), 2 lines: a panel opened by Enter focused its heading, then was filled again
  when its numbers came and the focus fell to the page body, so done item 3 failed on Q74's path. Now a panel
  filled again while the focus is inside it puts the focus on its new heading.
- Blocks: software-factory's loops run Σ → C → actuator → P's own summing point (where its flows add, disturbances
  with them) → P. Right and Left pass through that process-sum, so done item 2 reads as written (C, the actuator,
  P); the process-sum is still reached by Shift and an arrow. Where there are several ways on (the developer drives
  backlog's and in-review's), the walk takes the one on the shortest way back round the loop of the last Σ it was on.
- Not in the definition, added so that Q74's "everything clickable is reached by keyboard" still holds with one tab
  stop: Shift and an arrow step through every part in drawing order (the old Tab order, wrapping round). Without
  it the Open/Into buttons, loop markers and pins would have no keyboard way in. Removing it is 3 lines.
- Dynamics Right/Left on a part with no pipe (an auxiliary) fall back to any line out/in; Up/Down on a connector
  step to the focused part's next connector; Right/Left on a connector go to its ends. A connector's name now says
  its sign ("sign positive (+)", "sign negative (−)", "sign not known").
- "Home" is the top (then left) of the parts that a chain line (a pipe; Blocks' forward path) leaves and none
  enters; with none, the top-left part.
- The tab stop is remembered per view by `S.pinKey` (view, system, around), for the page's life.

Acceptance (tests/test_diagram_rendering.py; software-factory served, as the other page tests serve it, stands in
for :8791, which this container cannot reach):
- 1: `test_the_diagram_is_one_tab_stop_that_remembers_the_part_last_on` (both views).
- 2: `test_the_arrows_follow_pipes_connectors_and_signals` (Dynamics: backlog → submitted → in-review → its
  outflow → its stock and back, Down onto a connector naming backlog and a sign; Blocks: sum:backlog-clear →
  keep-backlog-clear (C) → developer (actuator) → backlog (P), Down → its sensor → the Σ, Left back). The test
  turns the page's line list round before walking (one `evaluate`, not a key), since the server lists pipes first
  and a walk that took any first line passed without it.
- 3: `test_enter_opens_the_panel_with_the_focus_inside_and_escape_returns_to_the_part` (both views).
- 4: `test_i_goes_into_a_system_and_escape_comes_back_out_onto_it` (both views, Escape and Backspace).
- 5: `test_the_focus_ring_is_the_accent_and_stands_3_to_1_in_both_themes` (the Dynamics view, light and dark: the
  outline and the stock's outline are the accent, ≥ 3:1 on the canvas). Blocks' ring is the same outline rule; its
  shapes' stroke is not checked there.
- Q74's `test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard` now enters by Tab and steps
  by Shift+Right, and checks exactly one tab stop per view.

Seen to fail with the code broken (lesson 9), each for its own reason: every part tabindex 0 (test 1: 182 stops);
the process-sum not passed through (test 2: P's summing point in place of P); Right taking any first line (test 2,
with the line list turned round: onto backlog's gap); the panel's refocus taken out (test 3: focus on the body);
Escape sent to the wrong system (test 4: timed out); the stock's ring rule taken out (test 5: the stroke is ink).

Run here: the six tests above (pass), tests/test_style_tokens.py (13 passed), ruff (clean). The whole of
tests/test_diagram_rendering.py, serially under the watchdog, twice: 296 passed, 31 failed (the first run 297/30;
watchdog rc 1, nothing killed). Not run here: the unit suite, the other three browser files, demo_check (no example
touched). Main is already merged into the branch (`git merge-base --is-ancestor main HEAD`). None of the 31 is in
code this branch changes, as far as could be checked here (`git checkout main -- <files>` to run them on main was
refused in this session, so they were not run on main):
- 21 × `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip[*]`: a `<title>` tooltip "Drawn alike
  here with B… changes-testing via fixer" in the Dynamics view (a loop marker's title, not keys.js).
- `test_every_view_draws_cleanly_and_in_time[autoscaler, the-job, ticket-factory]`: layout-rule ceilings
  (satellite-far, valve-orientation-mismatch).
- `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`: a 240 s draw timeout.
- `test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`:
  `get_by_role("button", name="fit")` (not exact) also matches the Blocks parts Q74 made buttons ("model-fits");
  the role and the names are Q74's, unchanged here (this branch changes only their tabindex).
- `test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout`: the dragged parts don't move. It
  failed the same way with this branch's roving stop and its focusin handler switched off (every part tabindex 0
  again, as on main), so it is not the roving stop.
- `test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back` (a ctrl-click's new tab never comes),
  `test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode` (legend rows),
  `test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words` (a response timeout),
  `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` (the Model page's "Nothing
  waiting."): none goes through the keyboard.
Left for the factory: run these 31 on clean main to confirm they are main's.
