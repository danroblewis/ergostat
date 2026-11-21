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
