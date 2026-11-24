# ui-open-frames-what-was-opened-fit-includes-every-w: Open frames what was opened, Fit includes every wire, and the edge hint says which way

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q71 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Open, Into, Fit)

**The problem:** After Open the opened system lands half off-screen under a large empty area; Fit still leaves wires and labels beyond the right edge; 'More beyond the edge' does not say where; the floating toolbar covers labels.

**The change:** After Open or Into, pan and zoom so the opened system's bounds are in view (at no less than the minimum text size). Fit uses the bounds of every node, wire and label. The hint reads 'more to the right / below' and is clickable to pan there. Keep the toolbar off the drawing's bounds.

**User stories it serves:** H2, A5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797 after Open on api, api's bounding box is wholly inside the canvas viewport or a hint naming a direction is shown; after Fit on :8791 ?view=blocks&system=modelling every path's and text's bounding box is inside the viewport and no hint is shown.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. 34 net lines in `ergostat/web/static/diagram.js` (+46, -12). Main has no commits past the branch's base, so there was nothing to merge.

- **Fit and the first view** now frame what is drawn (`drawnBox`: the `#viewport` group's `getBBox()`, so every part, line and label), not only the layout's box. They leave 60px clear above and below for the two floating toolbars.
- **The edge hint** is now a button. It names each way the rest lies ("More to the right and below") and, when clicked, pans most of a screen that way, no further than the edge.
- **After Open** (`showSystem`), the system stays where its box was if all of it is in view. Otherwise it is moved the least needed to bring it in, zooming out if needed but to no less than 0.8, the zoom the first view already treats as legible. If it is still too big, its top left goes to the top left of the view and the hint names the way to the rest.
- **After Into**, the view is fitted to the system drawn alone, as before. It now uses the drawn bounds.

Choices made without asking (each is easy to undo):
- The old rule was that an opened system stays exactly where its box was. Now it holds only when the system fits on screen. `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` was changed to match: a move is allowed only if the outline then lies wholly inside the canvas, and the pinned box's check takes off the pan.
- The demos on :8797 (api) and :8791 (modelling) are not in this clone. The tests use `examples/software-factory` instead: its top-level systems opened from their boxes, and `system=modelling` in Blocks and Dynamics.

Tests:
- New: `test_fit_shows_every_line_and_label_and_no_edge_hint[blocks|dynamics]` and `test_open_frames_the_system_opened_or_says_which_way_the_rest_lies`.
- I broke the code four times and the tests failed each time:
  - The drawn bounds replaced by the layout's box: Fit[blocks] failed (a text beyond the right edge, with no hint shown).
  - `showSystem` disabled: the Open test failed (factory's outline reached past the right edge).
  - No room left for the bottom toolbar: both Fit tests failed.
  - The hint text put back to "More beyond the edge": the Open test failed.
- `tests/test_diagram_rendering.py` run whole, serially, under the watchdog: 201 passed, 2 failed (rc 1).
  - `test_every_view_draws_cleanly_and_in_time[image-squeeze]` failed in the whole-file run and passed when run alone just after. I did not see its failure message: the summary line is all the run printed. It is not yet shown to be unrelated.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` fails again when run alone, at tests/test_diagram_rendering.py:3403. The /model page does not say "Nothing waiting." after a calibration is accepted. That is the Model page's list of proposals, which this change does not touch. I could not confirm it fails on main: putting main's diagram.js back to rerun the test was refused.
- Not run here: the other three browser files and the unit suite.

Round 1, after the factory's build step:
- The build step failed with rc 5. It chose `tests/test_diagram_rendering.py` (affected_tests) and ran it with no Playwright installed. That file skips as a whole at line 38 ("No module named 'playwright'"), so the run was "1 skipped", no test collected. No test ran and none failed, so there is no fault in the branch's code to fix. I left the code as it is.
- What is needed: run the build step for a browser-only selection with Playwright (`uv run --with playwright==1.63.0 ...`, as the browser suites run), or let it count a file skipped only for want of Playwright as not run instead of as rc 5. That change is in the factory's suite runner, outside this gap (lesson-13).
- Refused in this session: `uv run python -c "import playwright" ...; grep ...; uv run ruff check ergostat tests scripts` (Bash denied). So I did not run ruff or any test this time.

Round 2:
- No review findings to answer (none recorded for round 1). The code in `ergostat/web/static/diagram.js` is unchanged from round 1 (34 net lines).
- The build step's rc 5: added `test_the_served_diagram_script_frames_what_is_drawn_and_its_edge_hint_names_the_way` to `tests/test_graph_cli_web.py`, the same fix main took for the Agents page (ab17bb6e). The branch's changed tests now include a file that runs without Playwright, so the build collects something. The test fetches `/static/diagram.js` from the server and checks the text: Fit uses `drawnBox` (`getBBox`), not the layout's box; the hint is a button, names left/right/above/below and has a click; `showSystem` runs after Open in both views. It is a text check, weaker than the browser tests, which stay the real acceptance check. I broke the code twice and it failed each time: Fit put back on the layout's box (line 231), and the hint text put back to "More beyond the edge" (line 233).
- Ruff: clean.
- `tests/test_graph_cli_web.py`: 33 passed.
- The acceptance browser tests, with Playwright, under the watchdog: `test_fit_shows_every_line_and_label_and_no_edge_hint[blocks|dynamics]` and `test_open_frames_the_system_opened_or_says_which_way_the_rest_lies`: 3 passed, rc 0.
- `tests/test_diagram_rendering.py` whole, with Playwright, under the watchdog: 202 passed, 1 failed (rc 1, 23 min). The first try was stopped at my shell's 10-minute background limit before it printed anything, and I ran it again. `test_every_view_draws_cleanly_and_in_time[image-squeeze]`, which failed in round 1's whole-file run, passed this time.
  - The one failure: `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`, at tests/test_diagram_rendering.py:3403, the same as round 1. The /model page does not show "Nothing waiting." after a calibration is accepted. That text comes from `pages.js:1093`, the Model page's proposal list. This branch does not change `pages.js`, and none of its changed functions (`applyView`, `fit`, `drawnBox`, `showSystem`) appear in that path. I take it as unrelated (lesson-13) but have not shown that it fails on main. Refused: `git worktree add -q --detach /tmp/mainwt main && cd /tmp/mainwt && uv run ... named_tests.py tests/test_diagram_rendering.py::test_an_equation_...` (Bash denied), so the merge queue's run on main must settle it.
- Not run here: the other three browser files and the unit suite.

## Where it stopped

Parked by the factory (implementor, 2026-11-22 17:02).

Stopped on its last attempt by RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 166, in main
    return build(cfg, given, began)
  File "/Users/user/ergostat-live/instance/dev/bin/implement.py", line 221, in build
    got = fac.session(cfg, "implementor", prompt, work)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 678, in session
    out = agents.session(cfg, role, brief, work, keep=kept)
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 204, in session
    egress(cfg)
    ~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 117, in egress
    _egress(cfg)
    ~~~~~~~^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 124, in _egress
    docker("network", "create", "--internal", NET)
    ~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/user/ergostat-live/instance/dev/bin/agents.py", line 106, in docker
    raise RuntimeError(f"docker {args[0]}: {r.stderr.strip()[-300:]}")
RuntimeError: docker network: failed to connect to the docker API at unix:///Users/user/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/user/.docker/run/docker.sock: connect: no such file or directory

```

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 17:03).

Its runs failed past their attempts (a dead letter):
- attempt 13: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 14: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 15: nack exited 1
- attempt 16: nack the run ended with gap/ui-open-frames-what-was-opened-fit-includes-every-w still parked

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 18:30).

Its runs failed past their attempts (a dead letter):
- attempt 14: nack the implementor pool is full (run/pools.json): waits its turn
- attempt 15: nack exited 1
- attempt 16: nack the run ended with gap/ui-open-frames-what-was-opened-fit-includes-every-w still parked
- attempt 17: nack given back

## Where it stopped

Parked by the factory (dead-letters, 2026-11-22 19:06).

Its runs failed past their attempts (a dead letter):
- attempt 15: nack exited 1
- attempt 16: nack the run ended with gap/ui-open-frames-what-was-opened-fit-includes-every-w still parked
- attempt 17: nack given back
- attempt 18: nack given back

## Where it stopped

Round 1 (continued), after the factory merged main (af4bc34a):
- The merge conflicted in `tests/test_diagram_rendering.py` and `tests/test_graph_cli_web.py`. Both sides only added tests, so I kept both (fba7610d).
- After the merge, both cases of `test_fit_shows_every_line_and_label_and_no_edge_hint` failed. Main's toolbar now has a caption row and is 82px tall, so the fixed 60px left above the drawing was too little. Fit and `showSystem` now measure the two toolbars as drawn (`bars`), with 6px clear, and leave no room where a toolbar sits outside the canvas (the narrow layout). Before this, the constant made the Fit test fail, so that test catches this. The Open test's "top left in view" bound now reads the toolbar's bottom instead of a fixed 80px. The code is 39 net lines in `ergostat/web/static/diagram.js` (+51, -12), within the 60-line budget.
- Ruff: clean. `tests/test_graph_cli_web.py`: 43 passed.
- With Playwright, under the watchdog: the two Fit cases, the Open test and `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` passed (4 passed, rc 0).
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 254 passed, 32 failed (rc 1, 50 min; round 2 took 23 min and had 1 failure). The failures, from the pytest cache:
  - `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip` for 20 examples.
  - `test_every_view_draws_cleanly_and_in_time` for coordinator, image-squeeze and ticket-factory.
  - These nine: `test_a_big_tangled_model_lays_out_in_time_and_cleanly`, `test_every_part_opens_its_panel_when_clicked_even_mid_redraw`, `test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays`, `test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout`, `test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard`, `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`, `test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction[False]`, `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` (also failed in rounds 1 and 2) and `test_needs_attention_is_three_headed_groups_in_a_fixed_order`.
- Checked alone:
  - `…no_part_has_a_tooltip[first-loop]` fails because a part in the Dynamics view has a `<title>` "Drawn alike here with B10 changes-testing via fixer". This branch adds no title in the canvas.
  - `test_parts_chosen_with_a_box_…` (the parts do not move when dragged), `test_every_part_opens_its_panel_…` (no panel for a clicked stock) and `test_needs_attention_…` (a wait_for_function timeout) fail alone too. They kept failing with the branch's framing turned off for the run (`bars` at a fixed 60, `showSystem` returning at once, `drawnBox` giving the layout's box). The only branch code left on was the hint's text and its click. So I take these as coming with main's merge or this machine, not from the branch (lesson-13).
  - Not shown: that they fail on clean main. Refused: `git worktree add -q --detach /tmp/mainwt main && cd /tmp/mainwt && uv run ... named_tests.py ...` (Bash denied). Also refused: a background run writing to `/tmp/dr.log`. The other 28 failures were not looked at one by one.
- Left: the factory should run these failing tests again on clean main, and hold this gap until main is fixed or they are shown to pass there. Not run here: the other three browser files and the unit suite.

## Where it stopped

Round 2 (continued), after the factory merged main (7a905955):
- The merge conflicted in `ergostat/web/static/diagram.js` (the zoom bar's first two buttons) and `tests/test_graph_cli_web.py` (two tests added at the same place). I kept the branch's edge hint, which is a button, and added main's `aria-label` to Zoom out. I kept both tests (39c0e998). The code is still 39 net lines in `diagram.js` (+51, -12 against main).
- The review's finding: the record said the demos on :8797 and :8791 are not in this clone. That was wrong. :8797 is `examples/big` (api is `examples/big/systems/api.yaml`) and :8791 is `examples/ticket-factory`, which declares `modelling`. I take that back. The tests now check those demos (d756e954):
  - `test_fit_shows_every_line_and_label_and_no_edge_hint` runs on `ticket-factory` with `system=modelling` in Blocks and in Dynamics, and still on software-factory: 4 cases.
  - `test_open_frames_the_system_opened_or_says_which_way_the_rest_lies[big]` opens api from its box on big. The `[software-factory]` case is the old test, with Into still checked on its `factory`.
- Breaking the code to show the tests can fail:
  - `showSystem` returning at once: `[big]` fails. api lands at zoom 1.0 with its bottom past the canvas (b 848 of 800) and no hint. `[software-factory]` fails too.
  - `bars` giving no room for the toolbars: all 4 Fit cases fail. The drawing runs under the zoom bar.
  - `drawnBox` giving the layout's box: all 4 Fit cases still pass. Since main's merge, the layout's box takes in every line and label on these demos, so the drawn box makes no difference that a test can see here. In round 1, Fit[blocks] on software-factory failed with this break. It no longer does. The drawn box stays as a safeguard. No browser test now fails without it. Only the text check in `tests/test_graph_cli_web.py` does (lesson-9).
- Ruff: clean. `tests/test_graph_cli_web.py`: 48 passed. With Playwright, under the watchdog: the Fit, Open and `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` tests, 7 passed, rc 0.
- Refused: a Bash call that resolved the conflicts with a python heredoc and grep. I resolved them with the editor instead. Also refused: running the named tests wrapped in `cd /work; timeout 590 ...`. The plain form from the brief ran.
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 281 passed, 34 failed (rc 1, 57 min). All the new Fit and Open cases passed. What failed, from the run's own messages:
  - `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip`, for 21 examples. The cause is a `<title>` in the Dynamics view, "Drawn alike here with B.. changes-testing via fixer", the same as in round 1. This branch adds no title.
  - `test_every_view_draws_cleanly_and_in_time` for autoscaler (satellite-far 6 > 0), image-squeeze (routing took 20.97 s > 20 s), the-job (valve-orientation-mismatch 3 > 2) and ticket-factory (satellite-far 15 > 14). These are the layout rules' counts and a timing bound. The branch changes only the view's pan and zoom, not the layout.
  - `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`: a 240 s wait_for_function timeout.
  - `test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard`: `get_by_role("button", name="fit")` matches 5 elements (blocks whose labels contain "model-fits", and Fit). The edge hint is not one of them.
  - `test_every_part_opens_its_panel_…`, `test_parts_chosen_with_a_box_…`, `test_an_equation_…` ("Nothing waiting." missing on /model) and `test_needs_attention_…` (a 30 s timeout). These match round 1's failures that I checked alone.
  - New since round 1, and not looked at one by one: `test_blocks_crossings_hop_dots_…` (a 5 s wait timeout), `test_the_exported_png_shows_every_loop_name_…` (6 legend lines, wants more than 10) and `test_a_panel_open_on_what_is_chosen_stays_open_…` (a 120 s timeout waiting for a response).
  - None of these touch Fit, Open framing or the hint, as far as their messages show. But I have not shown that they fail on clean main (lesson-13). Left: the factory should run them again on main and hold this gap until main passes or they are shown to pass there. Not run here: the other three browser files and the unit suite.

## Where it stopped

Round 3, after the factory merged main (8a27f9e3):
- The merge conflicted in `docs/DESIGN.md`, `ergostat/web/static/diagram.js` and `tests/test_graph_cli_web.py`. I resolved it and kept both sides (7fa7c386):
  - `diagram.js`: main added a phone layout (`NARROW`, `fitNarrow`) and arrows in the edge hint ("More beyond the edge →↓"). I kept main's phone path in `fit`, before the branch's line. On wider screens, Fit still uses the drawn bounds and the toolbars as drawn. The hint is still the branch's clickable button with words, and main's arrow now follows each word: "More to the right → and below ↓". That keeps main's phone test (`test_on_a_phone_…`), which looks for an arrow in the hint. Choice made without asking, easy to undo: words and arrows both, not one or the other.
  - `tests/test_graph_cli_web.py`: I kept both sides' tests. The branch's text check now skips `fit`'s phone line (that line reads the layout's box, as main wrote it), and also checks that the hint holds all four arrows.
  - `tests/test_diagram_rendering.py`: the branch's two hint patterns now expect the arrows.
  - `docs/DESIGN.md`: I joined the branch's sentence about the hint and framing with main's sentence about phones.
- The code is 36 net lines in `ergostat/web/static/diagram.js` against main (+51, -15), within the 60-line budget.
- Ruff: clean. `tests/test_graph_cli_web.py`: 53 passed.
- With Playwright, under the watchdog: the Fit cases, the Open cases and `test_on_a_phone_the_diagram_opens_with_a_whole_system_box_in_view` passed (8 passed, rc 0). `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` and `tests/test_style_tokens.py` passed (14 passed, rc 0).
- Breaking the code: with the arrows taken out of the hint, `test_on_a_phone_…[software-factory]` failed (hint "More to the left", no arrow) and so did an Open case. With the arrows put back, both pass.
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 293 passed, 34 failed (rc 1, 59 min). All the Fit, Open and phone cases passed. The failures, from the pytest cache, are the same tests as round 2's:
  - `test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip` for 24 examples.
  - `test_every_view_draws_cleanly_and_in_time` for autoscaler, image-squeeze, the-job and ticket-factory.
  - `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`.
  - `test_every_part_opens_its_panel_…`, `test_parts_chosen_with_a_box_…`, `test_blocks_crossings_hop_dots_…`, `test_everything_clickable_…_by_keyboard`, `test_a_goal_name_opens_its_evidence_…[False]`, `test_the_exported_png_shows_every_loop_name_…`, `test_a_panel_open_on_what_is_chosen_stays_open_…` and `test_an_equation_…`. The last fails at tests/test_diagram_rendering.py:5413: there is no "Nothing waiting." on /model, as in every round. That text is from the Model page's proposal list, which this branch does not touch.
  - The run printed only the last failure's message, and I could not read the others: a Bash call that would list the pytest cache was refused (`uv run python -c "import json;..."`). I read the cache file with the editor instead. As far as rounds 1 and 2 showed, none of these is about Fit, Open framing or the hint. I have not shown that they fail on clean main (lesson-13). Left: the factory should run them again on main and hold this gap until main passes them, or they are shown to pass there.
- Also refused: `mb=$(git merge-base ...); git diff $mb 8a27f9e3 -- ...; grep ...`, and a `cat >> ... <<'EOF'` heredoc to append this section, which I wrote with the editor instead.
- Not run here: the other three browser files and the unit suite.

## Where it stopped

Round 4, after the factory merged main (dc8ad98d):
- There were no review findings to answer besides the queue's "conflicts with main: tests/test_graph_cli_web.py".
- The merge conflicted only in `tests/test_graph_cli_web.py`, where both sides added a test at the same place. I kept both: the branch's `test_the_served_diagram_script_frames_what_is_drawn_and_its_edge_hint_names_the_way` and main's `test_a_link_s_window_is_the_one_the_api_is_asked_for_and_its_address_is_the_page` (500d4c71). `diagram.js` merged with no conflict. The branch's code there is unchanged: 36 net lines against main (+51, -15), within the 60-line budget.
- Refused: a `python3 - <<'EOF'` heredoc to strip the conflict markers. I resolved them with the editor instead.
- Ruff: clean. `tests/test_graph_cli_web.py`: 55 passed.
- With Playwright, under the watchdog: the Fit and Open cases and `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` passed (7 passed, rc 0). So did `test_on_a_phone_the_diagram_opens_with_a_whole_system_box_in_view` (2 passed, rc 0).
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 302 passed, 36 failed (rc 1, 61 min). All the Fit, Open and phone cases passed. From the pytest cache, the failures are round 3's 34, plus two more:
  - `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`, which last failed in round 1. It fails alone too, at tests/test_diagram_rendering.py:2746. The Dynamics view's text says "goal" ("open · goal developer-honest cannot close …"), and the test forbids control words there. That is the view's wording, not Fit, Open framing or the hint.
  - `test_a_suggestion_appears_when_it_has_a_verdict` (new). It fails alone too, with a 20 s wait_for_function timeout. The test waits for Needs attention's loop entry and for the suggestions list, which this branch does not touch.
  - The other 34 are the same tests as round 3's, including `test_an_equation_…` (no "Nothing waiting." on /model, now at tests/test_diagram_rendering.py:5546).
  - None of them is about what this branch changes, as far as their messages show. I have not shown that they fail on clean main (lesson-13). Left: the factory should run them again on main and hold this gap until main passes them, or until they are shown to pass there.
- Not run here: the other three browser files and the unit suite.

## Where it stopped

Round 5, after the factory merged main (2f08c24e):
- The merge conflicted in `ergostat/web/static/diagram.js` (`applyView`) and `tests/test_graph_cli_web.py`. In `applyView` I kept main's new `sdSparksZoomed(svg)` call and the branch's edge hint. Main's side of the conflict was its own old "More beyond the edge" hint, which the branch's hint replaces. In the test file both sides had added a test at the same place, and I kept both (a141e6a3). I resolved them with the editor because a `python3 - <<'EOF'` heredoc was refused.
- The review's finding (diagram.js:873-876): the hint's click panned by(left) − by(right), each capped at 0.8 of a screen. When the drawing ran past both sides, the two cancelled and the click did nothing. Fixed (c91bb17b): on each axis the click now pans towards the side with more beyond it (on a tie, right and below), most of a screen and no further than that edge plus 60px. It pans only if that side has more than 2px beyond it. The hint's words still name every way the rest lies.
- New browser test: `test_the_edge_hint_pans_when_the_drawing_runs_past_every_side`. It uses software-factory with `system=modelling`: Fit, eight Zoom ins, and the drawing's middle put on the canvas's middle. It asserts the hint names all four ways, clicks it and asserts the view moved over 100px on both axes. With the old click put back it failed (`assert (0.0 > 100)`: no move). With the fix it passed.
- The code is 37 net lines in `ergostat/web/static/diagram.js` against main (+52, -15), within the 60-line budget.
- Ruff: clean. `tests/test_graph_cli_web.py`: 56 passed.
- With Playwright, under the watchdog:
  - The Fit cases, the Open cases and the new hint test: 7 passed, rc 0.
  - `test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins` and `test_on_a_phone_…`: 3 passed, rc 0.
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 307 passed, 38 failed (rc 1, 62 min). All the Fit, Open, phone and new hint cases passed. From the pytest cache, the failures are round 4's 36, plus these:
  - `test_sensors_…_no_part_has_a_tooltip` now fails for 26 examples, the same `<title>` cause as before.
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` fails alone too: "routing open=* took 20327ms", over a 20 s bound. That is the layout's routing time. The branch changes only the view's pan and zoom.
  - `test_a_valve_says_its_rate_inputs_and_equation_and_its_pipe_what_moves` (new) passed when run alone just after. So it fails only under the whole-file run, and its cause is not found (lesson-10).
  - The rest are the same tests as round 4's, including `test_an_equation_…` (no "Nothing waiting." on /model, now at tests/test_diagram_rendering.py:5574).
  - I have not shown that they fail on clean main (lesson-13). Left: the factory should run them again on main and hold this gap until main passes them, or until they are shown to pass there.
- Not run here: the other three browser files and the unit suite.

## Where it stopped

Round 6, after the factory merged main (278f54a4):
- The only finding was the queue's "conflicts with main" in docs/DESIGN.md, ergostat/web/static/diagram.js and tests/test_graph_cli_web.py. I resolved them with the editor and kept both sides (87db36f6). A `python3 - <<'EOF'` heredoc was refused, and so was a `git add … && git commit … && git log …` chain. The plain `git add` and `git commit --no-edit` ran.
  - `diagram.js` (`fit`): main gave the Process view's map a zoom of at least 1, so its 11px text is never drawn smaller. I put that floor on the branch's `k`. Fit still uses the drawn box and the toolbars as drawn. Main's side also had its own copy of the old layout-box framing, which the branch's framing replaces.
  - `docs/DESIGN.md`: I kept the branch's sentences about the hint and framing, and added main's Process-map notes for Fit and for phones.
  - `tests/test_graph_cli_web.py`: both sides had added a test at the same place, so I kept both.
- Main's new `test_items_links_each_kind_to_its_process_map_…` looked for the old hint text, "More beyond the edge ", and failed after the merge (the hint read "More to the right →"). This branch replaces that wording by design, so the test now checks for "More to the (left|right|above|below)" (65df4b31). Its 11px and arrow checks are as main wrote them.
- The code is 37 net lines in `diagram.js` against main (+52, -15), within the 60-line budget.
- Ruff: clean. `tests/test_graph_cli_web.py`: 58 passed.
- With Playwright, under the watchdog:
  - The Fit cases, the Open cases and `test_the_edge_hint_pans_…`: 7 passed, rc 0.
  - `test_opening_and_closing_…_keeps_the_pins` and `test_on_a_phone_…` (2 cases): passed.
  - The process-map test: passed after the fix above. `tests/test_style_tokens.py` passed too (16 passed, rc 0).
  - The three Process-view tests that go through Fit (`test_every_process_view_draws_its_workflows_cleanly`, `test_a_kinds_frame_dragged_…`, `test_process_view_with_no_kinds_…`): 25 passed, rc 0.
- `tests/test_diagram_rendering.py` run whole, with Playwright, under the watchdog: 320 passed, 35 failed (rc 1, 65 min). The Fit, Open, hint, phone and Process cases all passed. The pytest cache lists the 35 failures, all tests that failed in earlier rounds:
  - `test_sensors_…_no_part_has_a_tooltip` for 24 examples, from the same Dynamics-view `<title>`.
  - `test_every_view_draws_cleanly_and_in_time` for autoscaler, coordinator, the-job and ticket-factory. These are the layout rules' counts and a timing bound.
  - `…control_view…[autoscaler]`, `test_every_part_opens_its_panel_…`, `test_an_open_system_dragged_…`, `test_blocks_crossings_hop_dots_…`, `test_the_dynamics_view_speaks_system_dynamics_…`, `test_a_goal_name_opens_its_evidence_…[False]`, `test_a_suggestion_appears_…`, `test_the_exported_png_…`, `test_a_panel_open_on_what_is_chosen_…` and `test_an_equation_…`. The last fails at tests/test_diagram_rendering.py:5898: there is no "Nothing waiting." on /model, as in every round.
  - Not shown to fail on clean main (lesson-13). Left: the factory should run them again on main and hold this gap until main passes them, or until they are shown to pass there.
- Not run here: the other three browser files and the unit suite.
