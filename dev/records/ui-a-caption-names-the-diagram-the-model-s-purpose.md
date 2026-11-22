# ui-a-caption-names-the-diagram-the-model-s-purpose: A caption names the diagram, the model's purpose and the verdict

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q02 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (all views)

**The problem:** The home page has no h1, the SVG has no name, and nothing says which discipline's diagram this is or what the model is for. The model's purpose sentence is never shown.

**The change:** One line under the view switch, which is the page's h1 and the SVG's accessible name: 'Stock-and-flow diagram (system dynamics) · the-job: <purpose> · 2 systems · 28 goals, 2 off' and 'Block diagram (control) · … · 16 control loops, 2 off'.

**User stories it serves:** A1, G1, H5

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
/diagram has exactly one h1; it contains the project's purpose text and the view's diagram type; the diagram svg has aria-labelledby pointing at it; switching to Blocks changes the type words.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1, 2026-11-22)

**Built** (302de41b). `/api/status` sends `purpose` (the model's `purpose:`), `top` (the number of top-level systems)
and `controlled` (the goals whose loop has a controller). `ergostat/web/static/diagram.js` draws one `h1#diagram-caption`
as a row of the view toolbar, under the view switch. The svg has `aria-labelledby="diagram-caption"`. The caption is
updated on each draw. The CSS keeps it on one line, as wide as the toolbar's controls, with the rest elided and the
full text in its title. A short bullet was added to docs/DESIGN.md. About 31 net lines of code, under the 60 budget.

**Choices made alone (the reversible ones):**
- "goals" (Dynamics) are every goal in the status's loops. "control loops" (Blocks) are the goals a controller holds
  (`spec.loop(g).controllers`). "off" is a loop whose status is `off`. If the definition meant other counts, only
  `captionText` and the `controlled` field change.
- "N systems" counts the top-level systems (`spec.subsystems(None)`), which matches the "2 systems" of the-job.
- A model with no purpose shows its name alone. The Process view shows its type ("Process map (process mining)"),
  the model and its systems, and no goal count. A count the status does not send (an old snapshot) is left out,
  not shown as 0.

**Tests.** `tests/test_diagram_rendering.py::test_the_diagram_has_one_caption_naming_its_type_the_models_purpose_and_its_verdict`
passes. It checks exactly one h1, the type words and the purpose (Dynamics, then Blocks clicked), the svg's
aria-labelledby, that the caption sits under the switch on one line, and that the counts match the status. It was seen
to fail with two breaks: no aria-labelledby on the svg, and Blocks given the Dynamics words. Not exercised: a non-zero
"off" count, because the-job is served without running and every loop reads 0 off.
ruff is clean. tests/test_graph_cli_web.py and tests/test_web_access.py pass (57).

**The whole of tests/test_diagram_rendering.py, run serially: rc 1, 5 failed, 196 passed (53 min).** Each failing test
was run again alone, with main's page code put back by hand (the caption, the status fields and the svg attribute taken
out):
- `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]`: they fail on main too ("routing
  open=* took 31.4s / 31.9s", against a 20s bound). That is libavoid's speed in this container.
- `test_a_big_tangled_model_lays_out_in_time_and_cleanly`: it fails on main too ("[open=*] took 3037ms to draw",
  against 2500).
- `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: it fails on main too, with the same
  assertion ("Nothing waiting." missing from the Model page).
- `test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it`: it passes alone
  on main and passes alone on the branch, three times out of three. Its assertion in the full run was not captured:
  the output was cut to its tail, and pytest's lastfailed cache names it only. So this failure is unexplained, not
  shown to be unrelated. The branch moves nothing it drags: the caption only adds a row to the toolbar, which floats
  over the canvas. The merge queue's run should name it if it comes back.
Not run here: tests/test_items_page.py, tests/test_page_polling.py, tests/test_page_refresh.py, the unit suite and
demo_check (no example was changed). main had nothing new to merge (local main 2468c59b is already in the branch).
Refused commands: `git checkout main -- ergostat/web`; named_tests.py given three test ids at once.

## Where it stopped (round 1, after the fast suites, 2026-11-22)

The factory's `build` step failed with rc 5. Its tail shows why: `affected_tests` picked only
tests/test_diagram_rendering.py, the build step ran it without Playwright (`could not import 'playwright.sync_api'`),
the module was skipped, and pytest returned 5 (no tests ran). No test failed. No assertion was reached. So there is no
code to fix, and no code changed in this round. Run with Playwright under the watchdog, the acceptance test
`tests/test_diagram_rendering.py::test_the_diagram_has_one_caption_naming_its_type_the_models_purpose_and_its_verdict`
passes (rc 0, 1 passed). The build step needs Playwright (or `build_browser = true`) to judge a page-only change. That
is the factory's setting, outside this gap.

## Where it stopped (round 1, second build failure, 2026-11-22)

The build failed again the same way (rc 5: its one selected file, tests/test_diagram_rendering.py, skipped without
Playwright). The server half of the change, the status's `purpose`, `top` and `controlled`, had no test outside the
browser file. So this round adds one:
`tests/test_graph_cli_web.py::test_the_status_says_the_models_purpose_its_systems_and_its_controlled_goals`. It serves
the-job with a purpose in-process and checks the purpose, the 2 top-level systems, and that `controlled` is sorted, not
empty and a proper subset of the loops. The changed file is now picked by `affected_tests`, so the build runs a real test
without Playwright. It was seen to fail with two breaks of ergostat/web/server.py, each put back afterwards: every goal
counted as controlled, and the purpose sent as "". The whole of tests/test_graph_cli_web.py passes (32), and ruff is
clean. No code outside tests/ changed in this round.

## Where it stopped (round 2, merge of main 720426bd, 2026-11-22)

The one finding was the conflict with main in tests/test_diagram_rendering.py. Both sides had added a test at the end
of the file: this branch's caption test and main's `test_needs_attention_is_three_headed_groups_in_a_fixed_order`
(with `GROUPED` and `GROUPS`). The merge keeps both, unchanged (d81035b2). No code changed. On the merged tree, with
Playwright under the watchdog, the caption test and main's new test both pass (rc 0, 2 passed). The status unit test in
tests/test_graph_cli_web.py passes, and ruff is clean. Not run here: the rest of the browser files and the unit suite.
Those run in the merge queue.
