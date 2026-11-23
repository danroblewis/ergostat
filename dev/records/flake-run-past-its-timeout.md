# flake-run-past-its-timeout: test_a_run_past_its_timeout_is_stopped_with_what_it_started stops failing in parallel runs

`tests/test_runner_and_state.py::test_a_run_past_its_timeout_is_stopped_with_what_it_started` failed in 5 of the last 30 merge runs and passes alone.

Likely cause, to confirm: the test looks for leftovers with `pgrep -f "sleep 30"` across the whole machine, then runs `lsof` on each pid (`_child_of_test`). In a parallel run that sees other tests' processes, and a process can exit between `pgrep` and `lsof`.

Change. Check the run's own process group or a marker unique to this test (for example a unique sleep duration or a pid file the child writes), so another test's process can never be counted and a process that has already exited is not an error. If the runner truly leaves a child behind, fix the runner. Do not skip, retry, quarantine or add a timeout.

Definition of done.
1. The cause is named in the record.
2. The test no longer inspects processes it did not start.
3. It still fails if the runner leaves the run's child alive (show this by breaking the kill).
4. Passing 30 times under load is checked by the coordinator after review: do not run a load test in the session, and do not park the gap for it.

## Where it stopped

Built, round 1. Test-only change; no code outside `tests/` changed (0 net lines against the 600 budget).

Cause (done item 1). The check was not looking at this test's processes. After the run, it listed every `sleep 30` on the machine (`pgrep -f`), and `_child_of_test` counted any pid whose cwd held both `/repo` and `pytest`. About eighteen other test files also start `sleep 30`, many from the `repo` fixture's pytest tmp folder, so in a parallel run another test's live `sleep 30` was counted as this run's leftover. On top of that, a pid that exits between `pgrep` and `lsof` was read with no error handling, and `lsof` is missing on Linux hosts, where any stray `sleep 30` made the test raise `FileNotFoundError`. The runner itself does not leave a child behind: `_kill` SIGKILLs the run's whole process group (`start_new_session=True`), so `ergostat/runner.py` is unchanged.

Change (done item 2). The test makes its own fifo (`alive`) in its tmp repository and opens the read end. The run's script opens the write end, starts `sleep 30` holding that fd (with stdin, stdout and stderr on /dev/null, so the runner's own pipe cannot be what notices it), and writes `started`. After `run_agent` returns, the test reads the fifo to end of file. End of file comes only once every process holding the write end has exited. The test then asserts it read `started` (the child really ran, so the test cannot pass with nothing to check) and that end of file came within the test's existing 10 s bound. It never looks at the process table, so another test's processes cannot be counted, and a process already gone is just a closed fd. No skip, retry, quarantine or new timeout: the 10 s bound and the 1 s agent timeout are the ones the test already had.

Shown failing (done item 3), each break made by hand in `ergostat/runner.py::_kill`, run once, then reverted:
- `os.killpg(...)` replaced by `p.kill()` (the leader only): fails at the first assertion (the run takes 30 s, since python keeps the runner's stdout open).
- `pkill -KILL -P <leader>` plus `p.kill()` (the leader and its direct children, so the grandchild `sleep` lives): the run returns in time and the test fails at the new check, "the run's own children were not stopped with it", after 30 s.

Risk left: if the run's python takes more than the 1 s agent timeout to start and write `started` under heavy load, the test fails with "the run never started its child" instead of passing with nothing checked. That failure names the cause; it is not a silent pass.

Not run (done item 4): the 30-run load check, left to the coordinator as the definition says.
