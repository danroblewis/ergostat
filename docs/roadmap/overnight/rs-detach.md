# rs-detach: a run's process no longer depends on the engine that started it

depends-on: [lease-race-resumed]

First of four parts of upgrades that keep runs going (owner, 2026-11-20). This part changes **no behaviour at a switch**.

## Definition of done
- A run starts in its own session, its output goes to its run log file (no pipe the engine holds), and the engine follows that file. A run record in the state folder holds pid, process start time, run id, lease and block.
- Streamed output, timeouts, stop and exit codes behave as before.
- Process start time works on macOS and Linux, and the wrapper runs under bash 3.2 and dash.

## Risks
Replacing the pipe touches **every** run: compare run-start latency and thread count with main, and report both.

## Files to touch
`ergostat/spec/engine.py`, the run/stream code it uses, `tests/test_resilience.py`.

## Acceptance tests
- `tests/test_resilience.py::test_a_run_keeps_going_when_its_engine_is_killed`
- `tests/test_resilience.py::test_a_detached_runs_output_and_exit_are_recorded_once`
- `tests/test_resilience.py::test_a_run_record_detects_a_reused_pid`

## Size budget
150 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built. Net lines outside `tests/` and `docs/`: +53 against main (`runrecord.py` +75 new, `engine.py` +13/-4,
`stream.py` +44/-75), inside the 150 budget.

**What it does.** `ergostat/spec/runrecord.py` (new) holds a run's four files in `runs/` of the state folder, named by
its run id (`RUN.in`, `RUN.out`, `RUN.exit`, `RUN.json`), plus the POSIX `sh` wrapper, `start_time(pid)` (Linux:
`/proc/PID/stat` field 22; elsewhere, i.e. macOS: `ps -o lstart=`) and `alive(record)`, which is true only while the
pid's start time still equals the recorded one. `Engine.run_block` writes the run's input to `RUN.in`. It starts the
wrapper in its own session, with stdin from that file and stdout to `RUN.out` (stderr goes to the block log as
before). It writes `RUN.json` (pid, start, run, block, lease `{item, fence}`) and follows `RUN.out` with
`stream.follow`, which replaces `stream.pump`. The files are removed once the run has been read to its end. Taking
up a run left behind by a dead engine is not built (a later part); nothing changes at a switch.

**Choices made alone (the most reversible ones, each a line or two to undo):**
- Exit codes as before. The wrapper catches INT and TERM, so a signal to the group leaves it waiting for its command
  (a caught signal is the default again in the command). When the command ended by a signal, the wrapper ends itself
  by the same signal, so `returncode` is still `-N`. The cost: a command that *exits* with 129..159 on purpose is now
  reported as killed by that signal (`-N`), since `sh` can't tell the two apart.
- End of a run. The old pump read until every holder of the pipe had closed it (for a killed run: until 2 s after it
  ended). A file has no such end, so a run now ends when its process has ended and its process group is empty, or
  2 s (`GRACE`) after its process ended, whichever comes first. The difference: a process the run left running *with
  the run's stdout* used to keep the run open with no limit; now it is cut off after 2 s. A process it left in its
  group with its output sent elsewhere now holds the run open for up to 2 s, where before the run ended at once.
  `test_streamed_output.py::test_a_fenced_runs_later_lines_are_refused_at_once` depends on this grace: its late line
  comes from python after the `sh` that started it was sent TERM.
- `RUN.exit` is written directly (an empty file means no exit yet), not through tmp+mv. That saves one process per run.
- A record whose start time can't be read counts as gone (`alive` is false). That never takes another process for
  the run. A later part that takes up runs must not read "gone" as "ended" unless `RUN.exit` is there.
- The output file grows with everything the run prints until the run ends (the pipe buffered 64 KB). It is removed
  at the end, and it is not capped here.

**Measured** on Linux in the container, in-process, for the changed path only: main's `stream.pump` (loaded with
`git show`) against the branch's wrapper, files and `follow`. The benchmark was a throwaway pytest file, not
committed, because making a worktree of main was not allowed here.
- Run latency, `echo 1`, 30 in a row, median: main 0.6 ms, branch 2.7 ms (p90 1.0 vs 3.6 ms). The extra comes from
  the wrapper's `sh`, writing the files and record, and the first look at the file (after 1 ms). The first version,
  with a 5 ms first look and an `mv`, measured 6.6 ms; the changes above cut it to 2.7 ms.
- A run's first line after a pause can arrive up to 50 ms late: when nothing is new the follower looks every 50 ms,
  where the pipe woke at once. 20 runs of `sleep 1; echo 1` at once: 1.02 s on main, 1.08 s on the branch.
- Threads: the same. 20 runs at once peak at 22 threads on both (one per run, the main thread and the watcher).
- Not measured: macOS, where `start_time` forks a `ps` for each run (expect a few ms more per run start).

**Tests.** The three acceptance tests, plus `test_a_runs_timeout_and_stop_still_end_it` and
`test_the_run_wrapper_records_the_exit_under_each_shell[sh|bash|dash]` (dash, and bash 5 here). bash 3.2 (macOS's
`/bin/bash`) was not run; the wrapper uses only POSIX `trap`, `[ ]`, `$(...)`, `kill -l`, `kill -s` and `printf`.
Each acceptance test was seen to fail with the code broken: stdout back on a pipe (the engine-killed test fails,
though at a missing output file rather than at the run dying), the final partial line dropped (the recorded-once
test fails), and `alive` comparing only the pid (the reused-pid test fails). Run one file at a time, all of these
pass: test_resilience, test_streamed_output, test_run_costs, test_spec_engine, test_leases, test_lease_kill,
test_parallel_runs, test_spec_blocks, test_runner_and_state, test_daemons, test_leased_workspaces,
test_gated_actions, test_decisions, test_claims, test_improve. I did not run the full unit suite under `-n 8` or the
browser suite (the factory runs them). This clone has no origin remote, so there was no origin/main to merge; the
branch is up to date with local main.

Round 2. There were no review findings to answer. One problem is still open, and it blocks: commit 1227723b ("work
the session left uncommitted") added `.bench/test_bench_detach.py`, the throwaway benchmark from round 1. It is a
scratch file, and the definition's files to touch don't name it. It has to come out (`git rm -r .bench` and a
commit). In this session, removing files was refused (`git rm` was denied twice), so it is still on the branch. I did
not try any other way to delete it. The code is unchanged since round 1, and the round 1 numbers still stand. Run
again this round, one file or a few at a time, all passing: test_resilience (31), test_streamed_output (10),
test_spec_engine (10), test_run_costs + test_leases + test_lease_kill (53), test_parallel_runs + test_spec_blocks +
test_runner_and_state + test_daemons (88). `ruff check ergostat tests scripts` is clean. Checked again: a timeout or
stop still sends SIGKILL to the run's group (`runner._kill`), so the wrapper's INT/TERM trap does not keep a killed
run going (lesson-6).

Round 3, after the factory's scratch-file gate refused `.bench/test_bench_detach.py`. Its removal was refused again
this session: `git rm -r .bench` was denied by the session's permission mode, the third session in a row. I did not
get around the denial another way (`rm`, `git update-index`, a revert of 1227723b). It reads as a deliberate block on
deleting files, so the next step belongs to whoever can delete them. **What is left:** one command and a commit,
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`. This only deletes the file; nothing
else in the gap needs to change. Nothing else changed this round. No code was touched, so the suites were not run
again.

Round 4, the same refusal. `git rm -r .bench` was denied again by the session's permission mode, the fourth session
in a row. As before, I did not get around it another way (`rm`, a revert, `git update-index`). Removing the file is
the only thing left, and someone allowed to delete files has to do it:
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`. No code changed and no suites were run.
Running another implementor session with the same permissions will be refused the same way.

Round 5 (the factory's "round 3"), after main (31cffd8f870e) was merged into the branch: the same refusal, the fifth
session in a row. `git rm -r .bench` was denied ("don't ask" permission mode), and as before nothing else was tried to
delete it. `.bench/test_bench_detach.py` is still tracked; it is the only thing left. No code changed. After the merge of main,
test_resilience (31), test_streamed_output and test_spec_engine (20) pass, one file at a time, and ruff is clean.
The full unit suite and the browser files were not run here; those and the removal are what is owed:
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, then the factory's suites. A sixth
implementor session with these permissions will not get further. This needs a person, or a session allowed to delete
files.

Round 6 (the factory's "round 3" again): the sixth refusal. `git rm -r .bench` was denied by the "don't ask"
permission mode, and nothing else was tried to delete the file. Nothing changed: no code, and no suites were run. The
only thing left is `git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, run by a person or by
a session that is allowed to delete files, then the factory's suites. Sending this item back to an implementor with
the same permissions will not move it.

Round 7: the seventh refusal. `git rm -r .bench` was denied by the "don't ask" permission mode, and nothing else was
tried to delete the file (no `rm`, revert or `git update-index`). No code changed and no suites were run. What is left
is the same: a person, or a session allowed to delete files, runs
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, then the factory's suites. Sending the
item back to an implementor with these permissions will not end this loop; the factory has to allow the deletion or
stop re-queuing it.

Round 8 (the factory's "round 4"), after main (278666f7349a) was merged into the branch (9f0ec90e): the eighth
refusal. `git rm -r .bench` was denied by the "don't ask" permission mode, and nothing else was tried to delete the
file. No code changed. After the merge, test_resilience (31) and test_streamed_output + test_spec_engine (20) pass,
and `ruff check ergostat tests scripts` is clean. Not run: the full unit suite and the browser files. Still left, and
only a person or a session allowed to delete files can do it:
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, then the factory's suites.

Round 9 (the factory's "round 4" again): the ninth refusal. `git rm -r .bench` was denied by the "don't ask"
permission mode, while a read-only `git status` in the same session was allowed. So the block is on deleting, not on
the shell. Nothing else was tried to delete the file (no `rm`, revert, `git update-index`, or overwriting it with an
empty file). No code changed, main was not merged again, and no suites were run. What is left has not changed: a
person, or a session allowed to delete files, runs
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, then the factory's suites. Sending the
item back to an implementor with these permissions will be refused the same way.

Round 10 (the factory's "round 4" again): the tenth refusal. `git rm -r .bench` was denied by the "don't ask"
permission mode. Nothing else was tried to delete the file. No code changed, main was not merged again, and no suites
were run. What is left is still one command and a commit, for a person or a session allowed to delete files:
`git rm -r .bench && git commit -m "rs-detach: the stray benchmark removed"`, then the factory's suites. Sending this
item back to an implementor with these permissions has now failed ten times in a row.
