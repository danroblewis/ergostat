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

## Where it stopped
Built, round 1. 0 net lines outside `tests/` and `docs/`.
- The reload entry now names the coordinator. The released lease entry stays in the file as a `# Released:` comment line, which `fac.quarantine` skips. It keeps who added it (the coordinator), why, and the evidence for its release. This was a choice nobody could confirm: deleting that one line undoes it.
- The 10 runs: each ran `pytest -q -n 8 --dist worksteal -rA tests/test_leases.py tests/test_reload_in_place.py tests/test_factory.py` under `scripts/suite_watch.py`, one after another (the unit suite's own flags, on a 3-file slice of 123 tests rather than the whole suite, which the implementor must not run itself). The lease restart test printed PASSED in all 10 runs, so it is released. Runs 3 and 5 each failed 2 other tests, both named in run 5: `tests/test_leases.py::test_renewed_by_events_and_expired_when_silent_then_retried` and `::test_the_watchdog_renews_from_what_the_holder_does_elsewhere`. This branch does not touch them (lesson 13). They are load flakes for their own gap.
