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

## Where it stopped (round 1, after the build step)

- The factory's `build` step gave rc 5, not a test failure: `affected_tests.py` picked the one test file the branch
  changed, tests/test_diagram_rendering.py, and ran it with `uv run python -m pytest` and no Playwright, so the
  file's module-level `importorskip('playwright.sync_api')` (line 38) skipped it whole ("1 skipped", no tests
  collected, pytest's rc 5). No test ran, so none failed.
- Nothing in the branch's code can change that: the change is page script and style, and the only test that can
  check it is a browser test (the definition asks for one, in this file). Making the step green would mean adding
  Playwright to `[suites] build` in dev/factory.toml or having scripts/affected_tests.py treat rc 5 / browser-only
  selections differently. Both are factory changes outside this gap (lesson 13), so they are not made here; they
  belong in their own gap. The reversible choice: leave the code as it is.
- The two acceptance tests were run with Playwright in round 1 and passed (above); the browser files run in full in
  the merge queue.

## Where it stopped (round 1, second build-step failure)

- The same rc 5 again: `affected_tests.py` ran tests/test_diagram_rendering.py without Playwright, the file's
  module-level `importorskip` skipped it whole ("1 skipped"), and pytest returned 5 (nothing collected). No test ran
  or failed. The branch's code has not changed since the round-1 build.
- There is no code fault to fix. Turning the step green needs a change outside this gap: Playwright in
  `[suites] build`, or `affected_tests.py` handling a browser-only selection (or rc 5) differently. A dummy unit test
  added only to give the step something to run would be a test that can't fail (lesson 9), so none was added. Left
  as it is (the reversible choice). The factory fix belongs in its own gap, and the browser file runs in full in the
  merge queue.

## Where it stopped (round 2)

- No review findings to answer (none recorded). main (277a9c6c) is merged in (d2998067). The merge changed other
  lines of style.css and left this gap's lines as they were (`git diff main -- ergostat/` is the same 8 lines).
- After the merge: the two acceptance tests pass with Playwright under the watchdog (2 passed, 8.7 s, rc 0), and
  `uv run ruff check ergostat tests scripts` is clean.
- The factory's build step will still give pytest rc 5 on this branch, for the reason given in round 1: the only
  changed test file is a browser file that skips whole without Playwright. dev/factory.toml and
  scripts/affected_tests.py are unchanged on main, and fixing them is outside this gap (lesson 13). The code is left
  as it is (the reversible choice). The factory fix belongs in its own gap, and the browser files run in full in the
  merge queue.
- Not run here: the unit suite, the rest of tests/test_diagram_rendering.py and the other three browser files (left
  to the merge queue, as the rules say).
- Refused here: a `cat >> <record> <<'EOF' ... EOF && git add && git commit` command, used to append this section
  in one step. It was written with the editor instead.

## Where it stopped (round 2, build-step failure)

- The same rc 5 as rounds 1 and 2: `affected_tests.py` selected only tests/test_diagram_rendering.py, ran it without
  Playwright, and its module-level `importorskip` (line 38) skipped it whole ("1 skipped", nothing collected). No
  test ran or failed; the branch's code is unchanged since round 2.
- There is no code fault in the gap to fix, and the step cannot go green from inside the gap: it needs Playwright in
  `[suites] build` or `affected_tests.py` treating a browser-only selection (rc 5) differently, both factory changes
  (lesson 13), or a unit test added only to give the step something to run (lesson 9). None was made; left as it is,
  the reversible choice. This gap waits on a factory gap that fixes the build step for browser-only branches.
- Refused here: a `python3 - <<'EOF' ... EOF && git add ... && git commit ...` command used to append this section
  and commit it. It was written with the editor instead.

## Where it stopped (round 2, second build-step failure)

- Same rc 5, same cause, fourth time: `affected_tests.py` selected only tests/test_diagram_rendering.py and ran it
  without Playwright. The module-level `importorskip` (line 38) skipped the whole file ("1 skipped in 1.51s"), so
  nothing was collected and no test ran or failed. The branch's code has not changed since round 2. `[suites] build`
  in dev/factory.toml and scripts/affected_tests.py are as they are on main (checked again).
- Moving the tests would not help. The definition puts them in a browser file, and every browser file skips whole
  without Playwright. No code was changed, the reversible choice. This gap waits on a factory gap that makes the build
  step run browser-only selections with Playwright, or not count their rc 5 as a failure (lesson 13). The merge queue
  runs the browser files in full.

## Where it stopped (round 3)

- No review findings to answer (none recorded). main is still 277a9c6c, already merged in; nothing new to merge.
- The build step's rc 5: main has since shown the way out (ab17bb6e, for the Agents page's gap, which had the same
  problem): a real unit test, in tests/test_graph_cli_web.py, that the build can run without Playwright. This round
  does the same, so the factory is not changed (lesson 13). The test is not there only to give the step something to
  run (lesson 9). It checks what the change rests on:
  `test_a_process_view_with_no_kinds_is_answered_empty_and_the_page_says_so_over_the_canvas` serves a copy of big
  and checks three things. Big's `/api/graph?view=process` has no nodes and no kinds, so the page takes its empty
  branch. The served diagram.js holds the new wording and its Dynamics link. The served style.css lays
  `.canvas-wrap > .empty` over the canvas (absolute, inset 0, centred). The browser half (the text's box is inside the
  canvas) is still the two browser tests named in round 1.
- Seen to fail when the change was broken (made with the editor, then put back): with `position: absolute; inset: 0`
  taken out of the overlay rule it failed at the rule assertion; with the old wording ("the process map draws how
  items moved") it failed at the wording assertion.
- Code unchanged: `git diff main -- ergostat/` is the same 8 lines (diagram.js +5 −2, style.css +3).
- Runs: the new test passes, and all of tests/test_graph_cli_web.py passes (33 passed, 8.4 s). The two browser
  acceptance tests pass with Playwright under the watchdog (2 passed, rc 0, 10.2 s). `uv run ruff check ergostat tests
  scripts` is clean. Not run: the factory's build command itself, the unit suite, the rest of
  tests/test_diagram_rendering.py and the other browser files (left to the factory and the merge queue).
- Refused here: a compound command that broke style.css and diagram.js with `sed -i`, ran the test after each break
  and restored them from /tmp copies. The breaks were made and undone with the editor instead.
