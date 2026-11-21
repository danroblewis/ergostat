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
