# quarantine-list-honest: the quarantine list names who really added each test, and releases the fixed one

depends-on: []

`tests/quarantine.txt` credits both entries to "the owner". The coordinator quarantined them; the owner asked only that flaky tests not block. The lease restart test is quarantined for the shutdown race, which `lease-shutdown-race` fixed on main (an audit ran the test 10 of 10 green).

## Definition of done
- Both entries name the coordinator as who added them.
- `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` is released, after 10 consecutive passes under the suite's own `-n 8` load, reported in the gap's result. If any run fails, it stays quarantined with that evidence.
- `tests/test_reload_in_place.py::test_a_removed_blocks_run_still_takes_messages_while_it_goes` stays until its own cause is fixed.

## Files to touch
`tests/quarantine.txt`.

## Risks
- lesson-8: the file's claim about who and why is what happened.

## Acceptance tests
- `tests/test_factory.py::test_the_quarantine_list_parses_with_who_when_why`

## Size budget
5 net lines of code outside `tests/` and `docs/`.
