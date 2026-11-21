# switcher-actually-runs: The upgrade switcher and the pipeline watch actually run on their schedule

depends-on: []

Audit 2026-11-21: `switch-drain` has never run. `goal: drains-within-bound` (`dev/model/landing.yaml`) generates a controller that commands the switcher, and the engine removes commanded blocks from its schedule (`ergostat/spec/engine.py`). The goal only goes off during an overrunning drain, and only the switcher can start one: 0 runs, 29 open requests. Approving `switch-instance` does nothing. `pipeline-watch` on main has the same trap (`dev/model/manager.yaml`); the live factory only works through a hand edit. Tests call `drain.step()` directly, so none noticed.

## Definition of done
- The switcher and `pipeline-watch` run on their schedule, whatever their goals read. Their goals are still read by something.
- `ergostat check` reports any block with `every:` whose schedule a generated controller removes, so this trap cannot be merged again.
- An approved switch, run through the real engine on a disposable instance, drains and switches to the newest version.

## Files to touch
`dev/model/landing.yaml`, `dev/model/manager.yaml`, the check code in `ergostat/`, `tests/test_factory.py`.

## Risks
- lesson-9: a test must use the engine's real schedule, not call the step directly.

## Acceptance tests
- `tests/test_factory.py::test_the_switcher_is_on_the_engines_schedule`
- `tests/test_factory.py::test_the_pipeline_watch_is_on_the_engines_schedule`
- `tests/test_factory.py::test_check_reports_a_schedule_a_goal_removes`
- `tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine`

## Size budget
60 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. I made these decisions alone (nobody to ask), each time taking the option easiest to undo:

- **The fix is in the model, not the engine.** The switcher reads `goal.drains-within-bound` and `pipeline-watch` reads
  `goal.no-stuck-gaps` as inputs (`in:`) instead of naming them (`goal:`). No controller is generated, so nothing
  commands them, and the engine's clock (`Engine._plan`) starts them every 1m / 5m whatever the goals read. Each goal
  is still read, by its block, which is the controller of the goal's loop. The engine's rule that a commanded block
  leaves the clock is unchanged: `goal:` with `every:` is a documented pace (SPEC §9.1) that other blocks rely on.
- **The check is a craft note (`schedule-removed`, `ergostat/spec/craft.py`), not a finding.** `goal:` with `every:`
  is also how the modelling template paces its own blocks (improver, fixer, modeller, redesigner use `every:` as a
  pace). The hand-wired fixture and `plan-lint` do the same. Nothing in the model's structure separates a pace that
  was meant from the trap. Even "only the block itself can set its goal off" does not show in the links: the
  switcher's drains are drawn as driven by the approved stock. So a finding would fire on correct models and change
  the finding counts that other tests and the modelling loop read. As a note, `check` lists it, and `--json` gives
  it with its code. Parts a template made are left out, as for every craft note. The note covers every block with
  `every:` or `cron:` that a generated controller commands. The test shows that main's model gets the note on both
  blocks, and that the branch's factory model gets it only on `plan-lint`. That one is a pace and stays as it is
  (outside this gap). A new block like this would fail the unit suite.
- **The engine test** builds the real `Engine` on the factory's whole model in a disposable instance (the fixture's
  folder, with its own record). It takes the timed blocks from the engine's own `_plan` and starts the switcher the
  way `_schedule` does (`start(b, "schedule")`), twice. Its runs call the real `ergostat` CLI on that record. The
  approval is a real gated `switch-instance` request, approved through `gate.approve`. The switch's own process
  (`live.py switch`) then moves `current` to the newest version (using fake versions, like the other switch tests).
  The test does not run the loop thread itself, because that would start every timed sensor and block of the factory.
- Not done here: origin/main could not be merged (this clone has no `origin/main`); the merge queue merges it and runs
  the suites. Net code outside tests, docs and dev: +10 lines (`craft.py`), within the budget.

### The unit suite stopped after round 1 (the suite-fix session)

The factory's unit run stopped at 9% (316 tests passed) with no failure, no pytest summary and no `suite_watch` JSON
line. `suite_watch` prints that line even when it kills the run for threads or memory, and when it is interrupted, so
the run was stopped from outside it: by the slot's time limit or the container. This session had no shell (every
Bash call was refused), so I could not run the suite or a single test, reproduce the stop, or commit anything. This
note is left in the worktree, uncommitted. Read-only findings:
- Only `test_an_approved_switch_drains_and_switches_through_the_engine` (marked `slow`, so `conftest._slow_first`
  starts it first on a worker) builds an engine on the factory's model and starts processes. Its waits all have
  deadlines (2 × 120 s, then 90 s). Its detached `live.py switch` runs only fake versions in the test's own `live/`,
  with the test's own `ERGOSTAT_HOME` and `FACTORY_CONFIG`. It holds no lock and leaves no thread that could stop the
  other seven workers.
- No other test runs an engine loop on the factory's model, so taking the switcher and `pipeline-watch` off `goal:`
  starts no new runs anywhere else in the suite.
- None of the `serial` tests (the only way one test holds back every worker) touches what this branch changed.
I found nothing in the branch that explains a stop of the whole run, and changed no code on a guess. Left: run the
unit suite again under `suite_watch.py`. If it stops at the same place, run
`tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine` alone with `-x -s` to see
whether it hangs.

### The unit suite stopped again, at 12% (the second suite-fix session)

This session could run pytest one file at a time, but not other commands. Measured:
- The switch test alone passes in 72 s; the two schedule tests pass in 77 s. All of `tests/test_factory.py`, serially:
  74 passed, 2 skipped, 208 s. Nothing hangs, and nothing outlives the tests.
- Almost all of that time is the fixture's `read(ROOT / "ergostat.yaml")`, which runs the extreme-conditions tests.
  They are kept in memory per process (each test has a home of its own). The first read in a process stops at the
  60 s `BOUND` (branch: 78 of 459 conditions not run). The second finishes the rest (13.7 s). The model as main has it
  costs the same (60 s, 66 not run, then 11.5 s), so the branch's model edit does not add to it.
- The one cost the branch did add: `test_check_reports_a_schedule_a_goal_removes` read a second whole model (main's
  version) with its extremes. That is about 40 s more CPU on one worker, and a fourth run of the full extremes in the
  same process. It now reads the two models with `extremes=False` (the note is a craft note, and is still read: the
  test still finds `block.plan-lint`). It runs in 0.95 s, and it still fails when the check is broken: that was tried.
  This changes a test's cost, not its bounds or what it asserts.
Still not found: why the whole run stopped with no failure and no `suite_watch` line. A stop from outside, with
nothing in pytest printed, fits a slot or container limit. That limit is not in this repository (`dev/factory.toml`
gives `unit` no timeout). If the next run stops at the same place, run main's unit suite in the same slot and see
whether it stops too. If it does, the stop does not come from this branch (lesson-13).
