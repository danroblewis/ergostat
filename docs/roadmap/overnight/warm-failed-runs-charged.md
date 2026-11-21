# warm-failed-runs-charged: Warm runs that crash or hang report their CPU

depends-on: []

Audit 2026-11-21, reproduced: warm runs are charged only on `done` (`ergostat/daemons/proc.py`), so a crashed or hung run has no `resources` after burning CPU. These are often the costliest runs, and GAPS says each run is charged.

## Definition of done
`fail_all` and the timeout path charge each run what it used, or record it as unknown when it cannot be read.

## Files to touch
`ergostat/daemons/proc.py`, the warm daemon tests.

## Risks
- lesson-3: unknown is recorded as unknown, never zero.

## Acceptance tests
- `tests/test_daemons.py::test_a_crashed_warm_run_is_charged`
- `tests/test_daemons.py::test_a_timed_out_warm_run_is_charged`

## Size budget
25 net lines of code outside `tests/` and `docs/`.
