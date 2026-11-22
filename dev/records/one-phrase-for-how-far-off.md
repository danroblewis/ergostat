# one-phrase-for-how-far-off: Outside Blocks, how far a goal is from its bound is said in one phrase from one function

depends-on: []

Problem (R11 piece 5): the same goal reads 'desired = 0: excess 37', 'setpoint ≤ 0 (off by 36)' and 'error −36' on three surfaces (shots/story-6-g1-home.png, infod-tf-loops.png, ixdb-job-sd-open.png). Filed Q23 makes the bound's writing uniform; the distance from it is still worded three ways. In Blocks 'e = -36' is the discipline's form and stays.
Change: one server function words the distance for every non-Blocks surface from the goal's bound kind and error: 'off by 36 tickets' (past a ≤ or ≥ bound), '28 short of 180' (below a setpoint), '12 over 80%' (above), 'within its band' (inside a band), with the unit and filed Q82's number words; the goal's state carries the phrase (`off_by_words`; it joins the goal row's fields when goal-row-one-renderer has landed). The Goals page, the side list, the Dynamics gap, the evidence's first line and attention entries print it; Blocks keeps e with its sign. No page code formats an error itself.
Definition of done:
1. On a fixture one goal's distance reads the same on the Goals page, the Dynamics side list, its gap and its evidence panel.
2. In Blocks the same goal still reads 'e = ...'.
3. A unit test covers ≤, ≥, setpoint with band, and a goal with no unit.
4. grep finds no 'excess' or 'off by' string built in pages.js, diagram.js, dynamics.js or details.js.
Files: ergostat/state.py (the phrase), ergostat/dynamics.py, ergostat/web/static/pages.js, diagram.js, dynamics.js, details.js, tests.
Acceptance tests: the unit test; a browser agreement check on the fixture.
Budget: 50 net lines.

Milestone: r11-one-word-each. Owner items: R11 piece 5. From the owner's list and the design review of 2026-11-22.

## Where it stopped

Built (round 1), 19 net lines, inside the 50-line budget:
- `state.off_by_words(setpoint, error, tolerance, unit)` is the one function. The state's loop carries it as `off_by_words`; graph.py passes it to the controller node as `offBy`, which the Dynamics gap node reads.
- These print it: the attention entry for a loop that is off (`setpoint <= 5 (+1) (off by 7 tickets)`), Dynamics' attention cards (`desired backlog = 5: off by 7 tickets`), the Loops page's 'how far' column (formerly 'error'), the gap's panel row (`now off by 7 tickets`), the loop panel (the evidence) and its crossings, and the control view's feedback-line panel. The crossings needed server.py to word each recorded `loop.off` from its own setpoint and error.
- Blocks (blocks.js, blockdiagram.py) is untouched. It keeps `e = r − y_m` and the signed e chart; the browser check pins this.

Choices made with nobody to ask (each easy to undo):
- Filed Q82's number words are not on main, so the number is written with the existing `state.fmt`. When Q82 lands, `off_by_words` is the one place to change.
- The unit goes on the bound for a setpoint (`28 short of 180 tickets`, `12 over 80%`) and on the distance past a bound (`off by 36 tickets`). The `%` is attached to the number.
- Beyond the four named forms: `within its band` for any bound when 0 < |e| ≤ tolerance, `within its bound` for a one-sided goal at e = 0, `on its setpoint` for `==` at e = 0, and None when the error or bound is unknown.
- The gap node still draws its value as a number on the canvas, since it is a system dynamics variable. Only its panel row prints the phrase.
- Files outside the list: graph.py (one field) and web/server.py (the crossings), both needed for a surface the definition names.
- The goal-row-one-renderer gap has not landed, so `off_by_words` is not yet among the goal row's fields.

DoD 4, read narrowly: no distance string ('off by', 'excess N', `by ${fmt(error)}`) is built in the four files, and none of them formats an error. A literal grep for 'excess' still finds dynamics.js lines 481, 538, 554 and 600. Those name the system dynamics variable itself (Sterman's 'excess', in the legend, the glossary and the gap panel's row label), not a distance, so they stay.

Tests: tests/test_off_by_words.py (≤, ≥, setpoint with band, no unit, attention and Dynamics cards). tests/test_diagram_rendering.py::test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks checks the Loops page, side list, gap and evidence all read 'off by 7 tickets', and that Blocks still reads e = r − y. Reverting the Loops page cell and the gap row made it fail ('−7' and the bare number). Then I restored the code.
All of tests/test_diagram_rendering.py: 196 passed, 5 failed. None of the failures touch this change. Two failed on routing time limits (`test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: 35 s against 20 s, failing again alone). Two failed on layout time: `test_a_big_tangled_model_lays_out_in_time_and_cleanly` (3.8 s against 2.5 s, failing again alone) and the Blocks drag test (passed alone). `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` fails at 'Nothing waiting.' on the Model page, on a model with no goal, so no phrase is involved. It failed again alone. I could not check these on main: `git checkout main` was refused in this session. test_page_polling.py: 17 passed, rc 0. The other two browser files and the full unit suite were not run here.
