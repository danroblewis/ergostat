# state-times-in-the-loop: the time-in-state goals are read by something that acts

depends-on: [manager-sessions]

Audit 2026-11-21: `state-times` (merged) added goals and auxiliaries that `ergostat check` reports as unfinished: 47 `missing-feedback` (no block reads the goal), 45 `auxiliary-without-causes`, 45 `collector-undescribed`. That is 137 of the 168 open modelling requests, and they bury the real ones. The owner wants these times as setpoints, so keep them and close the loops.

## Definition of done
- Each time-in-state goal in `dev/model/times.yaml` is read by a block that acts when it is off. The pipeline manager's trigger is the expected reader: a time goal off past its tolerance is part of what its next session sees.
- Goals nothing should act on become plain measures. Say which and why in the file's header. Prefer fewer goals: median and p90 for every state is not needed where one would drive the same action.
- Each auxiliary names its causes and each collector has a description.
- `ergostat check` reports none of the three findings for `times.yaml`.

## Files to touch
`dev/model/times.yaml`, `dev/model/manager.yaml`, `dev/bin/watch.py`, `tests/test_factory.py`.

## Risks
- lesson-3: a time that cannot be read is unknown, never on target.

## Acceptance tests
- `tests/test_factory.py::test_the_time_goals_have_no_check_findings`
- `tests/test_factory.py::test_a_time_goal_off_reaches_the_managers_session`

## Size budget
100 net lines of code outside `tests/` and `docs/`.
