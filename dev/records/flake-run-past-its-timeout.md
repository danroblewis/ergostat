# flake-run-past-its-timeout: test_a_run_past_its_timeout_is_stopped_with_what_it_started stops failing in parallel runs

`tests/test_runner_and_state.py::test_a_run_past_its_timeout_is_stopped_with_what_it_started` failed in 5 of the last 30 merge runs and passes alone.

Likely cause, to confirm: the test looks for leftovers with `pgrep -f "sleep 30"` across the whole machine, then runs `lsof` on each pid (`_child_of_test`). In a parallel run that sees other tests' processes, and a process can exit between `pgrep` and `lsof`.

Change. Check the run's own process group or a marker unique to this test (for example a unique sleep duration or a pid file the child writes), so another test's process can never be counted and a process that has already exited is not an error. If the runner truly leaves a child behind, fix the runner. Do not skip, retry, quarantine or add a timeout.

Definition of done.
1. The cause is named in the record.
2. The test no longer inspects processes it did not start.
3. It still fails if the runner leaves the run's child alive (show this by breaking the kill).
4. Passing 30 times under load is checked by the coordinator after review: do not run a load test in the session, and do not park the gap for it.
