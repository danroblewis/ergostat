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

## Where it stopped
- Done in the working tree: the five lines are added to `tests/quarantine.txt`, after the existing quarantined line,
  in its `test id | who | when | why` format, with `the coordinator` as who, `2026-11-21` as when and the given why.
  Grep confirms that each id names a test function that exists (test_daemons.py:296 and :613, test_leases.py:407,
  test_runlog.py:254, test_spec_auxiliaries.py:111). No test file and no code changed: 0 net lines outside `tests/` and
  `docs/`.
- `fac.quarantine` (dev/bin/fac.py:481) takes the id before the first `|` of each line that is not a `#` comment, so
  these five ids are read as written. It reads the list at the base ref (main), not from the branch, so they are
  deselected only once this lands on main. That is the existing design, not a gap.
- Not done: the implementor's shell was refused for every command (`git -C /work status --short` and a grep loop
  were both denied), so nothing was committed, and neither pytest nor ruff was run. The factory has to commit these two
  files (`tests/quarantine.txt` and this section) and run the suites itself.
- After the factory's unit run (one `F` at about 11%; the kept tail ends before the failure summary, so the failing
  test is not named there): no code or test is changed for it. The definition forbids editing any test or code, and
  `fac.quarantine` reads the list at main, so this branch's five lines deselect nothing in its own run. The likeliest
  failure is one of these five load-timing tests, which the gap exists to quarantine. If it is not one of them, it is
  outside this gap (lesson-13). On a quiet machine the five ids passed together (5 passed in 15.7 s), and
  tests/test_factory.py with tests/test_workspaces.py (the tests that read the quarantine list) passed 125, skipped 2.
  `ruff check ergostat tests scripts` is clean. The full unit suite was not run here (the factory runs it).
