# ui-a-view-with-nothing-to-draw-says-so-on-the-canva: A view with nothing to draw says so on the canvas

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q10 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram?view=process (big); /diagram top level of big

**The problem:** The Process view on big is a blank canvas: its empty-state text sits at y=900, below the canvas. The line 'No flows at this level: what crosses between these systems is information only' is drawn at y=−14 and never seen.

**The change:** Centre the empty-state text in the canvas at every width, with the reason and where to look instead ('No kinds of item in big: its parts are counted by sensors. See Dynamics.'). Draw the 'No flows at this level' line under the boxes.

**User stories it serves:** A5, H1

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8797/diagram?view=process at 1440x900 an element containing 'No kinds of item' lies wholly inside the canvas's bounding box; on :8797/ the text 'No flows at this level' has y within the viewport.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1)

Built, 8 net lines outside tests (diagram.js +3, style.css +3 net of the two changed lines; within budget).

- `ergostat/web/static/style.css`: `.canvas-wrap > .empty` is laid over the canvas (absolute, inset 0, flex-centred,
  pointer-events off except its link). That covers every empty state in the wrap (Process, Blocks, an empty model,
  loading, server not answering), since they all sat below the svg the same way.
- `ergostat/web/static/diagram.js`: the Process view with no kinds says "No kinds of item in <system, or the model's
  name>: its parts are counted by sensors. See Dynamics." where Dynamics is a link to the Dynamics view at the same
  level. The 'No flows at this level' line is drawn 24 px under the layout's bottom, not 14 px above its top. Judgement
  call, the reversible one: the layout's extent and the first fit are left unchanged, so views that don't show the
  note fit exactly as before.
- Tests (tests/test_diagram_rendering.py): `test_process_view_with_no_kinds_says_so_inside_the_canvas` (big at
  1440, 1024 and 600 wide, 900 tall: the text is wholly inside the svg's box and centred to within 40 px vertically,
  with the exact wording, and its link opens Dynamics) and `test_no_flows_line_is_under_the_boxes_and_seen` (big's `/`
  at 1440x900 with Flows only on: one note, inside the viewport, its top below the lowest system box).
- Seen to fail when the change was broken: with the overlay rule disabled the first test failed (the text was at
  y=949..966, below the canvas), and with the old y=-14 the second failed (the note was at y=94, above boxes ending at 809).
  A narrow-width rule (≤700 px) was tried and taken out: the test passed at 600 px without it.
- Unlike the problem statement, the old note was already within the viewport at 1440x900 (y≈94). It sat above the
  boxes, under the toolbar's band, so the test checks "under the boxes" as well as "in the viewport".
- Runs: the two new tests pass. `uv run ruff check ergostat tests scripts` is clean. The whole of
  tests/test_diagram_rendering.py, run serially under the watchdog, gave rc 1: 197 passed, 5 failed, 52 min
  (a first attempt was stopped at the 10-minute background limit before it finished):
  - `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]` (routing open=* took 43 s, bound
    20 s) and `test_a_big_tangled_model_lays_out_in_time_and_cleanly` (drawn in 3.6 s, bound 2.5 s): time limits in a
    52-minute serial run. The change adds no layout or routing work, only one text element in a level with no flows.
    These were not rerun.
  - `test_a_valve_turns_upright_when_its_pipe_runs_up`: passed when run alone straight after, so load.
  - `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: fails alone as well, on the
    /model page's text ('Nothing waiting.' missing). This change doesn't touch that page or its script. Not shown to
    fail on main: the command that would have run it with main's diagram.js and style.css
    (`git checkout main -- ergostat/web/static/diagram.js ergostat/web/static/style.css && ... named_tests.py ... ;
    git checkout HEAD -- ...`) was refused here. Left for the merge queue's run on clean main (lesson 13).
- Not run: the unit suite and the other three browser files (left to the factory and the merge queue, as the rules
  say). There is nothing to merge from main: this clone's `main` is the branch's base.
