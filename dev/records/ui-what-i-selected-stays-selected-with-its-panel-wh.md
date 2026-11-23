# ui-what-i-selected-stays-selected-with-its-panel-wh: What I selected stays selected, with its panel, when I switch view

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q63 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Dynamics ↔ Blocks)

**The problem:** Selecting the stock quality and switching to Blocks highlights the sensor H(s), not the process output, and the panel falls back to Needs attention. Clicking a flow's label opens 'Charts of the parts chosen' instead of its panel; in Blocks its panel is titled 'Valve'.

**The change:** Keep the panel open across the switch, titled in the target discipline's words: 'output y_quality of P_service', 'actuating signal u_tuner', 'reference r = 0.93 and its summing junction'. Map a stock to y at the process output. A plain click on a flow's label opens the flow's panel.

**User stories it serves:** G2

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8793 ?system=service select stock quality, switch to Blocks: within 1 s the element y_quality at the process output has the selection ring and the side panel's title contains 'y'; clicking the label 'quality-steps' in Dynamics opens a panel whose title contains 'quality-steps'.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. About 33 net lines of code (interact.js, diagram.js, dynamics.js), within the budget.

- What was found: a stock chosen in Dynamics already lit y_quality (with its ring) in Blocks, and H(s) along with it.
  The panel was lost because switching view goes through `route()`, which closes it. A flow's label click did choose
  the flow, but its panel waited for the `part/flow` answer before it showed anything. On a slow or loaded server,
  that left only the side panel's "Charts of the parts chosen" on screen; this was reproduced, intermittently, in
  image-squeeze `open=*`.
- Choices made with nobody to ask (the most reversible ones):
  - The sensor H(s) stays lit when its stock is chosen. The correspondence rule (correspond.py, DESIGN "One
    selection, two views") says a sensor H on a stock *is* the stock, and changing that rule is the owner's call.
    "Map a stock to y" is met by the carried panel opening on y_quality, and y has the selection ring.
  - The panel is carried only by the Dynamics and Blocks buttons, and only when a panel is open on the current
    selection. A panel closed before the switch stays closed.
  - A flow carried to Blocks opens its controller's actuating signal (the `u_<block>` wire), titled
    'actuating signal u_tuner'. A reference opens its r input, titled 'reference r = 0.93 and its summing junction'.
- The acceptance test is `test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words`. It
  serves image-squeeze afresh at `?system=service`, not the demo at :8793. Its 1 s is counted from when the block
  diagram is drawn, not from the click: a loaded machine can take longer than that to lay the diagram out.
- `test_a_valve_says_its_rate_inputs_and_equation_and_its_pipe_what_moves` now waits for the filled panel (its `dl`),
  because the panel now opens before its numbers arrive.

Round 2.

- Main (720426bd) merged in; its conflict in diagram.js (the view buttons) kept both main's " · what is …" words and
  the branch's `carryPanel()`.
- The review's one finding (lesson-9, the late `part/flow` answer): the acceptance test now has the race. It holds
  `**/api/part/flow/**`, clicks the label 'quality-steps' in Dynamics, switches to Blocks, releases the held answer,
  waits for its response, and asserts the panel is still 'actuating signal u_tuner' and its kind is not 'Valve'.
  With the `if (!wait.isConnected) return;` guard after the flow's `api` call in dynamics.js removed, the test fails
  (`'quality-steps' == 'actuating signal u_tuner'`); with it back, it passes. No code outside tests changed.
- tests/test_diagram_rendering.py run whole after the merge: 200 passed, 5 failed (an earlier whole run: 198/7, its
  names cut off). None is this branch's:
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: routing open=* took 23.9 s and
    21.4 s against a 20 s bound, under load; layout, which the branch does not touch.
  - `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`: two stocks' panels not filled within 3 s in the
    whole run; it passes run alone. The stock panel now opens before its numbers, which can only make it sooner.
  - `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`: the side panel says
    "Goals off", from main's cd71c13e (Needs attention in three groups); the branch does not change the side panel.
    It fails run alone too, so it fails on main.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: the /model page has no
    "Nothing waiting."; the branch does not touch that page.
