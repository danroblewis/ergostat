# main-diagram-rendering-green: the 15 quarantined diagram rendering tests pass again and leave quarantine

On 2026-11-24 the coordinator quarantined 15 tests of tests/test_diagram_rendering.py (main 828321bf, tests/quarantine.txt, the lines dated 2026-11-24) because they failed alone in the queue's container on main and held every batch for over four hours. One fails with `AssertionError: autoscaler: satellite-far: 10 instances, the ceiling is 0 (docs/layout-rules.md)`; another times out waiting for a response after a switch of view. They may have been failing on main for a while unseen, because the browser suite is skipped for batches that do not touch page paths.

Change. For each of the 15: find whether the code regressed (fix it) or the test is wrong or depends on how it is run (fix the test so it passes alone and in the suite), then remove its quarantine line. Record which merge broke each, if any.

Done. Each of the 15 passes run alone by id in the queue's container setup and in the browser suite; none is left in tests/quarantine.txt. Run tests by id only. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1. All 15 pass when run alone by id in this container (named_tests.py, Playwright 1.63, under
suite_watch). Their lines are deleted from tests/quarantine.txt, not kept as `# Released:` lines, because done says none
is left in the file; the reasons are here instead. Not run here: the four browser files whole and the unit suite (the
queue runs them). Outside tests/ and dev/ the only change is 3 lines of ergostat/web/static/diagram.js.

Each test: what failed, why, what changed, and the change that broke it. Where I name a commit and not a merge, I did not
trace the merge.

- `test_every_view_draws_cleanly_and_in_time[autoscaler]`: `satellite-far: 10 instances, the ceiling is 0`. The fixture
  was missing an entry: examples/autoscaler came in without one in tests/fixtures/layout_known.json (fc78b5c42, merge
  58471dafb, demo-observed-external-controller). Recorded at its count now: satellite-far 10, valve-orientation 0.
- `test_every_view_draws_cleanly_and_in_time[the-job]`: system=rhythm drawn 1466x571 (fit 0.846) against 729x534
  recorded; satellite-far 37 against 35. The example changed: rhythm gained capacity-steps and the capacity law
  (186e23fd2, merge fef9cae3f, the-job-person-steps-and-laws), with no sizes or ceilings recorded again. The 2 new
  instances are both `flow:capacity-steps`/`gap:alert-drafting-paced` (open=*, system=rhythm). Its size and ceiling
  recorded again by hand (RECORD_* env runs are not allowed in this session), at the values measured.
- `test_every_view_draws_cleanly_and_in_time[ticket-factory]`: satellite-far 15 against 14. Every instance is a goal's
  `gap:` part far from its flow. Those parts are drawn since dynamics-every-goal-drawn (d652e72fb, merge c594cf17c),
  which landed after the ceilings were recorded (2026-11-19). The ceiling is set to 15. Moving the gaps nearer is layout
  work outside this gap. This is the reversible choice: the ratchet holds from 15.
- `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram[autoscaler]`: a 240 s timeout on
  view=blocks&system=rescales. Rescales is the observed HPA, which has no goal and no block that acts, so the page
  rightly says "No control system here: no goal, and no block that acts." The test waited only for a drawing. Now a
  system drawn alone may end in that sentence (BLOCKS_OR_NONE), and the whole and open views must still draw. The test
  was wrong from when the example came in (merge 58471dafb).
- `test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known`: "goal" found in the side
  panel. Model housekeeping says "goal developer-honest cannot close" since attention-names-goals-as-goals (245d4283e,
  merge e06a8b81d). The test already set the attention groups' words aside ("the same in every view"), but only their
  heads and "none" lines. It now leaves out the groups' rows too.
- `test_uncoupled_systems_are_parallel_rows_…[big-systems0|the-job-systems1|software-factory-systems2]` and
  `test_rows_keep_their_outlines_when_a_coupled_system_opens_or_closes_in_place`: `TypeError: list indices must be
  integers`. Two tests defined `ROWS`: blocks-uncoupled-systems-parallel-rows (4b4d6d383, merge faa35c93c) and
  parts-belong-to-their-system (d48fcc954, merge 77f79a3fd). The later definition replaced the Blocks one when the two
  merged; each branch passed alone. The Blocks one is renamed BD_ROWS.
- `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: no "Nothing waiting." on /model after
  the accept. With k right, the residual finder (0466dbff1, finding-structure-from-residuals, 2026-11-22) still offers
  "arrivals reaches queue through a DELAY3, τ 30s". It is right to: the test's record stored each arrivals rate as the
  rate over the 30 s *after* the reading. Now each reading is the rate over the 30 s up to it, and the finder offers
  nothing (checked with a scratch run of proposals.make, accept and review.refresh). k is then estimated 2.998, so the
  proposal's text is matched by the same pattern the test's other checks use (3, 2.99…, 3.0…).
- `test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays`: two causes.
  (1) The press at 60% across product's grip landed on a connector's wide hit path (`gap:no-live-bugs → flow:filed-bugs`,
  drawn since merge c594cf17c). The test now presses a spot that belongs to the grip.
  (2) A real regression. After a new visit the parts were laid out differently inside product. layoutGraph's choice to
  keep the satellites' room (e3c52198b) compared the plain layout's fit after the pins had moved it with the other
  layout's fit before them, so a pinned system changed which layout was drawn round it. Fixed in diagram.js: each
  layout's fit is taken before the pins (`laidFit`). Nothing changes with no pins (orientValves leaves the size alone).
  Seen failing without the fix and passing with it. The pin, drag and loop-marker tests nearby pass with it.
  Which merge exposed (2) is not traced; probably the same goal parts (c594cf17c).
- `test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them`: `name="fit"`
  matched 14 buttons once parts got spoken names (model-fits; diagram-spoken-names, merge 87115fd50). It now uses
  `name="Fit", exact=True`, as the file's other tests do.
- `test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot`: the kind page draws state groups by default
  (waiting, working, done) since the-kind-page (1a5c9aa17, merge 1b0b233ff). The test opens `/items/ticket?states=all`,
  so it still checks each declared state.
- `test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes`: `SAID.some is not a
  function`. pages.js has had a top-level `const SAID` since cf462c635, which shadows the test's `window.SAID`. The
  test's name is now `window.__canvasSaid`.
- `test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode`: every legend row was
  in the export, but the guard `len(rows) > 10` failed with 7 rows. Product drawn alone has no junction or controller
  of its own: its goals' loops are drawn at the top level (blocks top level, probably merge c5b03ad41, not proven).
  The guard is now `>= 6`.

Not built: no `## Entry` for this gap. The record had none, and done allows only this section to be added.

The implementor's build step (`[suites] build`, scripts/affected_tests.py) failed with pytest rc 5. The only test
file this branch changes is tests/test_diagram_rendering.py, and the build runs without Playwright, so the whole file
skipped and nothing ran. affected_tests.py now leaves out a file that does `importorskip("playwright...")` when
Playwright cannot be imported, says so, and falls back to collection only when nothing is left, as for a docs-only
branch. The merge queue's browser suite still runs the file. This change is in factory tooling, outside the 15 tests.
It is the smallest change that lets this gap's build step pass, and it is easy to undo. The test is
tests/test_factory.py::test_a_browser_only_test_file_is_left_to_the_browser_suite_without_playwright.

### Round 2 (the two review findings; what round 1 says above about them is replaced by this)

- scripts/affected_tests.py (browser_only, review finding 1). Round 1 dropped any file whose text held
  `importorskip("playwright`, so a file that calls it inside a fixture or one test (test_agents_page.py,
  test_dashboard_page.py, test_export.py, test_walk_scripts.py and others) would have had its unit tests left out of
  the build, and a branch changing only such a file got a green collection-only build (fail-open). Now a file is left
  out only when its own top level calls `pytest.importorskip("playwright...")` (`skips_whole_without_playwright`, read
  with `ast`: a statement of the module, outside any def, class or if). Such a file skips whole without Playwright. An
  importorskip inside a function, a class or an `if`, or one only quoted in a string, leaves the file in. So does a
  file that cannot be parsed. I kept the change in this branch and did not move it to its own gap. Without it this
  gap's build cannot pass: its only changed test file skips whole without Playwright (pytest rc 5). It is still easy
  to undo. Tests: test_factory.py::test_a_browser_only_test_file_is_left_to_the_browser_suite_without_playwright now
  also shows a branch whose file has importorskip inside a test still runs that file. The new
  test_only_a_top_level_importorskip_of_playwright_makes_a_file_browser_only covers each form and four real files
  (test_agents_page, test_dashboard_page, test_export, test_walk_scripts) that must stay in, and checks that
  test_diagram_rendering is left out. With the round-1 substring check put back, the first test fails: the file was
  left out and only collection ran.
- `test_the_dynamics_view_speaks_system_dynamics_…` (review finding 2). Round 1 removed every `.att` row from the
  side-panel check, and its reason ("the same in every view") was false: the server rewrites the rows in this view
  (dynamics.attention, words()). The rows are checked again, and the test removes only the group heads and their
  "none" lines, as before round 1. `goal NAME` is set aside only for the model's own goal names
  (`sd_goal_said(goals)`, the same form words() keeps), so "goal is off" would still fail. Breaking the server's
  wiring (server.py's `sd_attention` call removed) did not fail the test at first. image-squeeze's rows ("goal
  done-as-meant cannot close: none of its valves acts on a flow of false-done") hold no word of SD_WORDS even
  untranslated, because SD_WORDS leaves out "valve" on purpose. So the test now also checks the rows alone: there must
  be one ("cannot close"), and no control word and no "valve" may be left once the kept goal names and part names
  are set aside (words() says flow there). It fails on "valves" with the wiring removed, and again with
  words()' translations emptied (dynamics._WORDS). With both restored it passes.

### Round 3 (the two review findings; what rounds 1 and 2 say above about them is replaced by this)

- scripts/affected_tests.py (finding 1: fail-open for browser files the browser suite never runs). A top-level
  browser file is now left out of the build only when the merge queue's browser suite runs it: `in_browser_suite()`
  reads dev/factory.toml, takes the `tests/*.py` that `[suites] browser`'s command names, and keeps only those that
  `browser_paths` matches (where it is set: otherwise the queue never runs the suite for a branch that changes only
  that file). Every other top-level browser file (test_inbox_page, test_sql_editor, test_promql_editor,
  test_forecast_panel, test_data_source_panels, test_dashboard_keep_page, test_dashboard_merge_queue, …) is still
  handed to pytest, so a branch changing only one gets rc 5 again, as before round 1. A config that cannot be read,
  or has no browser command, leaves nothing out (fail closed). The docstring and browser_only's say this. Tests:
  test_factory.py::test_a_browser_file_the_browser_suite_does_not_run_is_still_named (a file named nowhere, a file
  named but on no browser path, an unreadable config, a config with no browser command: each still named), and
  test_only_a_top_level_importorskip_… now checks that the shipped config's suite holds test_diagram_rendering and
  none of the seven files. The fixture repository of `affected()` now carries a dev/factory.toml (BROWSER_SUITE).
  Seen failing: with round 2's filter put back (no suite check), the new test fails on its first case
  (`--collect-only` for test_baz.py). With the fix, the three factory tests pass.
- `test_the_control_view_draws_every_example_cleanly_as_a_block_diagram` (finding 2: any empty system skipped
  unaudited). The empty canvas is now allowed only for a listed system: `NO_CONTROL_SYSTEM = {"autoscaler":
  {"rescales"}}` (the observed HPA: no goal, no block that acts). Every view is waited on for drawn-or-empty; a listed
  system must say "No control system here" (if it draws, the test fails and says to take it out of the list), and
  every other view (the whole, the open ones, each other system alone) must draw, or the test fails naming it. I
  chose a hand-kept allowlist over deriving "no goal and no block that acts" from the model, since a derivation in
  the test would share the server's reading and could empty with it. Broken both ways and seen failing: with
  server.py made to return no nodes for any `system=` other than rescales, it fails with
  `[view=blocks&system=modelling] draws no control system`; with modelling added to the list, it fails with
  `… draws a control system, though NO_CONTROL_SYSTEM lists it as holding none`. Both breaks reverted. With them
  gone it passes for autoscaler, the-job, ticket-factory, big, software-factory and image-squeeze (each by id, with
  Playwright, under suite_watch). The other examples were not run here (the queue's browser suite runs them).

Round 3 not run: the unit suite, the four browser files whole, demo_check (no example touched). main merged in:
already up to date with the clone's main. ruff clean. Outside tests/ and dev/, this round changes only
scripts/affected_tests.py.
