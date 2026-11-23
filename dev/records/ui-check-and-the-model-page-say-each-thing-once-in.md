# ui-check-and-the-model-page-say-each-thing-once-in: Check and the Model page say each thing once, in a table

depends-on: []

A quick UI fix from the design review of 2026-11-22 (eight designers walked the running demos blind, then briefed on the owner's intent, then tested 46 newcomer user stories; Q78 of 82). Quick path: a small, focused change to the page; test what the change touches, no unrelated work.

**Pages:** /check, /model

**The problem:** Check is 17 run-on sentences, 13 of them the same warning with different numbers, then 30 lines of 11 px grey prose joined by semicolons. Model repeats 'an integrator, from the model / its dead time: a step of u, or a step test' on nearly every row; its 'process, controller, scope' links are href='#' and land on an arbitrary place with every system open.

**The change:** Check: one table per kind of warning (part, R² or 'never moved', scaled error, points), sorted worst first, the advice once above it, each part a link to the diagram; notes as a list at body size. Model: group rows with the same identification ('12 loops: an integrator, not yet tested'); each link opens that loop's panel with its system framed.

**User stories it serves:** C6, G7

## Definition of done
1. The change above, and nothing outside it.
2. The acceptance check below holds, as a browser test in the existing browser test files where it can be (tests/test_diagram_rendering.py, tests/test_items_page.py or the page's own test file).
3. The owner's design rules hold: no new page, panel or view; the Dynamics and Blocks diagrams stay separate, each true to its discipline.

## Acceptance
On :8791/check no warning sentence longer than 80 characters occurs more than once; there is a table whose header includes 'R²'; on /model clicking 'process' for located-worked changes the URL to that loop's system and opens a panel whose title contains its process.

## Files to touch
The page's template, script and style under `ergostat/web/`, and the test.

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1: 47 net lines outside tests and docs (pages.js, review.js, web/numbers_api.py, control/loop.py).

- **Check.** `/api/exercised` now gives each finding's numbers as well as its sentence (not-exercised: why, says,
  span, readings; calibration-worse-than-mean: r2, nmse, n). The page draws one table per kind. Each table sits under
  its advice, said once. Rows are sorted worst first: never-moved before no-variation, then the longest record; for
  the calibration kind, the largest scaled error. Each part links to the Dynamics diagram. The static check's
  warnings and notes that say the same thing about several parts (`file:line: kind name: what`, e.g. eleven 'no
  description' notes) are also a table each, under their shared text. The remaining notes are a list at body size.
  Decision taken alone (reversible): grouping the static check's repeats is a generic rule on the message's shape,
  not a code. Without it the "no description" clause repeated about 20 times and the acceptance did not hold.
- **Model.** Loops whose identification reads the same are one group under a heading ('12 loops: an integrator,
  from the model; its dead time: a step of u, or a step test'). Each link has a real href. Decision taken alone
  (reversible): "that loop's system" is the set of systems its goal and stock are in, with their parents
  (`/api/loop-control` returns `systems`). The link opens `/diagram?view=blocks&open=<those>`, not `open=*` and
  not `system=`. located-worked's goal is in `making` but its stock `located` is in `intake`. Drilling into
  `making` alone would hide the process block in a closed box. So the URL reads `open=factory,intake,making`.
- **Tests.** `test_check_and_the_model_page_say_each_thing_once_in_a_table` (tests/test_diagram_rendering.py) runs
  on ticket-factory with `/api/exercised` answered by the server's own wording (`ex.said`, `ft.worse_than_mean`).
  It was seen to fail against three breaks: findings listed as sentences again, links opening `open=*`, and no
  grouping. `test_the_model_page_says_what_is_available...` now reads quality-held's 'not identified' from its
  group heading. The new fields are checked in tests/test_exercised.py and tests/test_extremes_closed.py.
- **Not shown.** The acceptance names :8791 (the owner's running demo). It was checked here on a served copy of
  ticket-factory, without its record.
- **Runs.** The full tests/test_diagram_rendering.py, serially in the container: 197 passed, 4 failed.
  `test_every_view_draws_cleanly_and_in_time[coordinator]` and `[image-squeeze]` failed on a routing time bound
  (33 s and 39 s against 20 s). `test_a_big_tangled_model_lays_out_in_time_and_cleanly` failed on a 2.5 s draw
  bound (3.3 to 4.1 s). These are diagram layout timings; this branch does not touch layout. The fourth was
  `test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page`: after an accept, the review
  queue does not say "Nothing waiting.". Earlier reviews record this test failing on another branch, and this branch
  does not change the queue box. The equation test and the big-model test also fail when run alone. None was
  compared with main: `git checkout main -- <file>` and `git worktree add --detach /tmp/main-check main` were both
  refused in this session, so the factory's rerun on clean main must settle them. Also run: tests/test_control.py
  (52 passed), tests/test_exercised.py (7 passed), the touched extremes test, and ruff (clean). Main has not moved
  since the clone (277a9c6c), so there was nothing to merge.

## Where it stopped

Parked by the factory (dead-letters, 2026-11-23 14:35).

Its runs failed past their attempts (a dead letter):
- attempt 13: nack queue: the push of af4bc34a9e4c (gap/dashboard-new-chart-forms) is requested
- attempt 14: nack queue: the push of f2f65f066ded (gap/milestone-every-gap-has-one) is requested
- attempt 15: nack queue: the push of 58471dafb951 (gap/compute-runs-on-config-continued-continued) is requested
- attempt 16: nack its process has been gone since the engine stalled at 12:28: released so the pool can take work
