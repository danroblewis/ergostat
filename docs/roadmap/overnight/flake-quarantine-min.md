# flake-quarantine-min: A quarantined test never reds the queue

depends-on: []

Replaces the parked `flake-quarantine`, which grew too large and hit the kill rule, partly on counting a skip as a pass. The owner: "we can disable the flakey tests, or run them without blocking and review them after."

## Definition of done
- `tests/quarantine.txt` lists each test with who, when and why. It starts with `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` and `tests/test_reload_in_place.py::test_a_removed_blocks_run_still_takes_messages_while_it_goes`.
- The queue, triage and implementor suites deselect those tests, then run them beside the suite without blocking, recording each result on its flake item from the whole log.
- A skip is never recorded as a pass. No automatic quarantine or release in this gap.

## Files to touch
`dev/bin/fac.py`, `dev/bin/queue.py`, `dev/bin/triage.py`, `tests/quarantine.txt`, `tests/test_factory.py`.

## Risks
- lesson-3: a run that could not be read is unknown, never a pass.

## Acceptance tests
- `tests/test_factory.py::test_a_quarantined_test_does_not_block_the_queue`
- `tests/test_factory.py::test_a_skipped_quarantined_test_is_not_a_pass`
- `tests/test_factory.py::test_a_quarantined_failure_is_recorded`

## Size budget
80 net lines of code outside `tests/` and `docs/`.
