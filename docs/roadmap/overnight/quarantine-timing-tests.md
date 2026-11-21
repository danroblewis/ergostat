# quarantine-timing-tests: five tests that fail by timing under load stop reddening the merge queue

depends-on: []

On 2026-11-21 the merge queue spent most of its time re-testing batches: in 4 hours these five tests failed 15 times across queue runs, each failure costing a test pass of about 8 minutes. They passed on the next pass with no change, and `test_a_short_lived_daemon_is_sampled_before_it_ends` passed 6 of 6 on a quiet machine on main and on the gap the queue had blamed. They wait a few seconds of wall-clock for something a loaded machine does late.

## Definition of done
1. `tests/quarantine.txt` gains these, in its format (`test id | who | when | why`), with `the coordinator` as who and "fails by timing under load (queue runs 2026-11-21)" as why:
   - `tests/test_spec_auxiliaries.py::test_a_memoryless_setting_stays_an_auxiliary_the_block_states_whole`
   - `tests/test_daemons.py::test_a_short_lived_daemon_is_sampled_before_it_ends`
   - `tests/test_leases.py::test_one_run_per_item_bounded_by_the_pool`
   - `tests/test_runlog.py::test_two_concurrent_daemon_runs_keep_the_daemons_stderr_out_of_both_files`
   - `tests/test_daemons.py::test_a_daemon_ignoring_cancel_is_restarted_and_its_other_items_given_back`
2. No test is deleted or edited, and nothing else changes. Quarantined tests still run beside the suite, without blocking.

## Files to touch
`tests/quarantine.txt`.

## Risks
- A quarantined test can hide a real regression. These stay visible on their flake items and are to be made independent of machine load by a later gap, then released.

## Acceptance tests
- The five ids are each on one line of `tests/quarantine.txt`, and the queue's suites deselect them (`fac.quarantine`).

## Size budget
0 net lines of code outside `tests/` and `docs/`.
