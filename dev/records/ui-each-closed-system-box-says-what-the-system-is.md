# ui-each-closed-system-box-says-what-the-system-is: Each closed system box says what the system is

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q01 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /diagram (Dynamics, top level and any level with closed systems)

**The problem:** A closed box says only 'N feedback loops inside'. The description each system already has shows only after a click, or as '…'. A newcomer cannot say what 'job' or 'product' is.

**The change:** Under the box name print the system's description ('textkit and its customers'). Remove 'N feedback loops inside' from the box; keep the count in the system's panel.

**User stories it serves:** A1, B6

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8792/ the box 'job' and on :8796/ the box 'product' each contain their description text; no SVG text on a closed box matches /feedback loops inside/.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped (round 1)

Built: `ergostat/web/static/dynamics.js` (`sdSystem`, plus a small `sdWrap`; +12/−3 net 9 lines). In Dynamics, a closed
system box shows its description under its name. It is wrapped to the box's width, two lines at most, and only text
past those two lines is cut with "…". The 'N feedback loops inside' line is gone from the box. The count is still on
the system's panel ("N feedback loops inside it or through it") and on the side list. Decisions made without anyone to
ask, each easy to undo: a system with no description keeps the old fallback, "a module: open it to see its structure".
A remote box still shows what the remote ergostat says. The box is not made wider for the description, so no layout
or size fixture changes. The Blocks drawing is not touched. `examples/the-job/README.md` now says the box says what
the domain is.

Tests: new `tests/test_diagram_rendering.py::test_each_closed_system_box_says_what_the_system_is[the-job-job,
software-factory-product]`. It serves each example (the-job is :8792 and software-factory is :8796 in the demos), and
checks that the box's text is exactly the description and that no text on any closed box matches /feedback loops?
inside/. I broke the code twice and watched the test fail each time: with the count put back in place of the
description, "job's box says '28 feedback loops inside'"; with the description shown and a count line added, "a closed
box still counts its loops". The old test `test_a_module_says_as_many_loops_inside_as_the_side_list_and_draws_no_port_squares`
checked the count this gap removes. It is now
`test_a_module_counts_its_loops_in_the_side_list_not_on_its_box_and_draws_no_port_squares`: no count on any box, the
side list still counts, and the port checks are unchanged. It passes.

Whole `tests/test_diagram_rendering.py` under the watchdog: 197 passed, 5 failed, 0 skipped, rc 1. One failure was the
old test above, now fixed. The other four also fail with main's box code put back (run alone, both ways), so the change
did not cause them: `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]` (routing open=*
about 40 s against a 20 s bound), `test_a_big_tangled_model_lays_out_in_time_and_cleanly` (open=* drawn in about 3.7 s
against 2.5 s), and `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page` ('Nothing
waiting.' not on /model). They are reported, not fixed (lesson 13). Ruff is clean. Not run: `scripts/demo_check.py
the-job` (the command `uv run python scripts/demo_check.py --shots /tmp/shots the-job` was refused; only that example's
README changed). Also not run: tests/test_items_page.py (that page is not touched), the unit suite, and a merge of main
(main is the base of this clone and has not moved). No screenshot of the box was taken.

## Where it stopped (round 1, after the build)

The factory's `build` step failed with rc 5: `affected_tests: 4 changed, running tests/test_diagram_rendering.py`,
then `SKIPPED [1] tests/test_diagram_rendering.py:38: could not import 'playwright.sync_api'`, `1 skipped`. The build
command (dev/factory.toml `[suites] build`) runs pytest without Playwright, and with `build_browser = false` the only
test file this branch changes is a browser file. So no test ran, and pytest reports "no tests collected" (rc 5). No
test failed. That is not a fault in the branch's code. The definition puts the acceptance test in
tests/test_diagram_rendering.py, so any branch that changes only a browser test file will hit the same thing. Changing
scripts/affected_tests.py or the build command is outside this gap (lesson 13) and is left for its own gap. One option
is to treat a selection that is entirely skipped browser files as collection only.

Run again with Playwright under the watchdog: `test_each_closed_system_box_says_what_the_system_is` (both cases) and
`test_a_module_counts_its_loops_in_the_side_list_not_on_its_box_and_draws_no_port_squares`, 3 passed, rc 0. Ruff is
clean. No code changed in this step.
