# timer-long-records: The state timer works on a long record

depends-on: []

Audit 2026-11-21 (reproduced): above 500 events `dev/bin/times.py` calls `ergostat events`, which is not a command (exit 2), and its bookmark is saved only at the end, so every later run fails on the same gap. The largest gap has 326 events. The test mocks that call. `times.py setpoints` was also never run, so the time goals' holds are guesses.

## Definition of done
The timer reads a gap of any length through a real command, and one unreadable gap does not stop the rest. Setpoints are derived from the record once and recorded.

## Files to touch
`dev/bin/times.py`, `dev/model/times.yaml`, `tests/test_factory.py`.

## Risks
- lesson-9: the test must run the real command.

## Acceptance tests
- `tests/test_factory.py::test_the_timer_reads_a_gap_past_500_events`
- `tests/test_factory.py::test_one_unreadable_gap_does_not_stop_the_timer`

## Size budget
30 net lines of code outside `tests/` and `docs/`.
