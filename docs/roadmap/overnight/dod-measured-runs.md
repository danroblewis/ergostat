# dod-measured-runs: the factory runs a definition's acceptance measurement that sessions cannot
depends-on: []

## Definition of done
- A factory command (dev/bin, e.g. `measure-runs GAP`) runs a parked or built gap's named acceptance measurement on its branch head: N runs (N capped, hard maximum 50, enforced at parse and run time) of a pytest selection under `scripts/suite_watch.py`, through the shared suite slot, optionally with the CPU loaded by a capped, watchdogged load (kill past 1,500 threads or 6 GB).
- Each run's rc and, for a failure, its traceback tail are recorded; the counts (passed/failed of N, head sha) are appended to the branch's record where review reads them, and the gap is sent back to review unchanged when all pass, or to fix with the failing traceback as its input when any fail.
- A run that cannot be read or was killed counts as a failure (never as a pass).
- dev/README.md (The pipeline manager) and the agent guide say when to use it; the first user is gap/lease-shutdown-race (30 loaded runs of -n 8 tests/test_leases.py).

## Acceptance tests
- tests/test_factory_measure_runs.py::test_counts_recorded_and_sent_to_review_when_all_pass
- tests/test_factory_measure_runs.py::test_a_failing_run_sends_the_gap_to_fix_with_its_traceback
- tests/test_factory_measure_runs.py::test_n_above_the_cap_is_refused
- tests/test_factory_measure_runs.py::test_a_killed_or_unreadable_run_counts_as_failed
(each with stand-in suites, no real load)

## Size budget
180 net lines outside tests and docs
