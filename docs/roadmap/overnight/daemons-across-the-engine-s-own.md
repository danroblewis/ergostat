# daemons-across-the-engine-s-own: every daemon's process group ended before the engine starts its process again in place
depends-on: []

## The gap (as found on main)

`ergostat/cli/running.py` starts the engine again in its own process in two ways:
- `_restart(p, args)`: `os.execv` for a new model name, format or store. It is reached after `r.close()`, so `Supervisor.close()` (`ergostat/daemons/supervise.py`) has already stopped the daemons in `slots` and `draining`. It misses (a) warm processes in `Supervisor.dying` and (b) any group a `_kill` thread is still waiting to SIGKILL. `_kill` threads are daemon threads, so the exec ends them between their TERM and their KILL.
- `_restart_hard(p, args, why)`: `runner.kill_all()` and then `_restart`. It is called from the wedged branch of `cmd_run` (before `r.close()`), from the engine watchdog's thread (`Watchdog`: `e.restart_hard`) and from the start-up watchdog (`spec/watchdog.py::startup`), which can run while `start_all` is still spawning daemons. Daemons are not touched. Their stdin pipes close at the exec (CLOEXEC), but a daemon that ignores EOF, or a child it started, outlives the engine with no parent supervising it.

## Definition of done

1. **A registry of live daemon groups, kept without the supervisor's lock.** In `ergostat/daemons/proc.py`: a module-level `GROUPS: set[int]`, a `GROUPS_LOCK` (a plain `threading.Lock`, held only for set operations and never across a wait, a signal or I/O) and a `CLOSING` flag.
   - `Process.__init__`, right after the `Measured(...)` spawn, takes `GROUPS_LOCK`. If `CLOSING` is clear, it adds `self.pid`. If `CLOSING` is set, it sends `SIGKILL` to the new group at once (`os.killpg(self.pid, SIGKILL)`, errors ignored) and adds nothing.
   - The check and the add happen under that one lock, so a daemon spawned while a restart is collecting groups is either in the restart's snapshot or killed by itself (lesson-1).
2. **Leaving the registry.** `supervise.killpg(pgid, wait)` removes `pgid` from `GROUPS` (under `GROUPS_LOCK`) when it returns because the group is gone (`os.killpg(pgid, 0)` or the signal raised `OSError`). Every way a daemon ends already goes through `killpg` (crash or restart via `_kill`, drained via `_kill`, a stale spawn via `_kill`, `close`). So after `Engine.close()` returns and the `_kill` threads finish, `GROUPS` is empty. Nothing is kept forever under a pgid the OS could reuse.
3. **`supervise.end_all(wait: float) -> list[int]`**, a module function that takes no `Supervisor` lock:
   - Under `GROUPS_LOCK` it sets `CLOSING` and snapshots `GROUPS`.
   - Outside the lock it sends `SIGTERM` to every group in the snapshot. It then polls them all against one shared deadline, `time.monotonic() + wait`, never a wait per group. It sends `SIGKILL` to each group still present and removes each from `GROUPS`.
   - `wait` is clamped to `0 <= wait <= 3.0` inside the function, whatever the caller passes (lesson-4). Total time is about `wait` plus one poll, however many daemons there are.
   - It returns the pgids it signalled.
   - An `OSError` other than "none left" (for example `EPERM`) counts as "cannot be ours any more": dropped, and the loop never retries it.
4. **Both restart paths call it before the exec.** `running._restart` calls `supervise.end_all(min(grace(), 3.0))` immediately before `os.execv`.
   - On the soft path, `Supervisor.close()` has already run, so this is a backstop. It catches `dying` processes and interrupted `_kill` threads.
   - `_restart_hard` reaches it through `_restart`, after `runner.kill_all()`. It does not call `Supervisor.close()`, `fail_all` or any `events.add` on the hard path, because what is wedged may hold those locks.
   - `_restart` prints one line naming how many daemon groups it ended, but only when the count is above 0.
5. **What is drained, stated exactly.** On the soft path the daemons are asked to `stop` and drained, as now. On the hard path they get no `stop` line: their groups get TERM, then KILL after at most 3 s. Their runs are not recorded by the old process. Their leased items come back when their leases end, as the watchdog's docstring already says for runs. SPEC §9.7 gets a bullet, "**ergostat restarting itself**", that says exactly this, and `spec/watchdog.py`'s docstring adds daemons to "Runs under way are stopped by a restart". The bullet claims no more than items 1–4 and their tests show (lesson-8).
6. `docs/GAPS.md`: the entry is removed. `docs/DAEMONS.md`: one sentence in its "ergostat stopping or restarting" material, matching SPEC.
7. Done as the house rules require: the unit suite and the four browser files at rc 0, ruff clean, origin/main merged in and the suites run again (lesson-7). No examples are touched, so no `demo_check`.

## Files to touch

- `ergostat/daemons/proc.py`: `GROUPS`, `GROUPS_LOCK`, `CLOSING`; registration in `Process.__init__`.
- `ergostat/daemons/supervise.py`: `killpg` removes groups from `GROUPS`; new `end_all(wait)`.
- `ergostat/cli/running.py`: `_restart` calls `end_all` before `os.execv`; docstrings of `_restart` and `_restart_hard`.
- `ergostat/spec/watchdog.py`: module docstring only.
- `docs/SPEC.md` (§9.7), `docs/DAEMONS.md`, `docs/GAPS.md`.
- `tests/test_daemons_restart.py` (new). Its daemon script is defined in the test file: a `deaf` program that ignores `SIGTERM` and EOF on stdin, starts a child (`sleep 600`) in its group and writes both pids to files.

## Risks

- **lesson-1 (check, then write).** Without the lock, a daemon could be spawned after `end_all` snapshots `GROUPS` and before the exec (the supervisor's tick or `start_all` on another thread, especially under the start-up watchdog). It would escape. The `CLOSING` check and the add share `GROUPS_LOCK`.
- **lesson-6 (work running after cancel).** This is the gap itself:
  - a daemon that ignores EOF and TERM, or its child, still alive after the exec;
  - a group whose TERM was sent by a `_kill` thread that the exec ended before its KILL.
  
  `end_all` must KILL the whole group (pgid, not pid) for everything in the registry, not only `slots`.
- **lesson-3 (fail open).** If `end_all` read the `Supervisor`'s lists, a wedged lock holder would block it. If it skipped a group whose signal raised, it would leave that group running silently. The registry needs no supervisor lock, and only "none left" or `EPERM` drops a group.
- **lesson-4 (no ceiling).** If each group got its own grace, 50 daemons × 10 s would hang the watchdog's last resort for minutes. There is one shared deadline, clamped to ≤ 3 s inside `end_all`.
- **lesson-5 (stale state, reused id).** If ended groups were never removed from `GROUPS`, a later `end_all` could signal a pgid the OS had reused. Groups are removed when `killpg` sees them gone, and `GROUPS` is checked empty after a normal close.
- **lesson-8 (claim wider than code).** SPEC must not say the hard path drains runs or sends `stop`. It does neither. The docs say only TERM, then KILL within 3 s.
- **lesson-9 (test that can't fail).** Each test below names the break that makes it fail. The implementor breaks each one and reports that it failed.
- **lesson-10 (load).** The bounded-time test compares against a sequential lower bound with wide margins and is marked `@pytest.mark.serial`. Waits poll with a deadline; no fixed sleeps.
- **lesson-13 (stay in the gap).** Supervisor restart policy, `runner.kill_all` and the engine watchdog's logic are unchanged.

## Acceptance tests

All in `tests/test_daemons_restart.py`. `os.execv` is monkeypatched in `ergostat.cli.running` to record that it was called, and whether every pid in the test was already dead at that moment, then raise a sentinel exception.

- `test_hard_restart_ends_a_deaf_daemon_and_its_child_before_the_exec`: an Engine with one `deaf` daemon block (via `test_daemons.setup`/`start`). With the Supervisor's `lock` held by another thread for the whole test (simulating the wedge), call `running._restart_hard(p, args, "test")`. It asserts:
  - the call returns (to the sentinel) within 6 s;
  - at the moment `execv` was called, both the daemon's pid and its child's pid were dead.
  
  Fails if `_restart` does not call `end_all` (both still alive, since they ignore EOF and TERM), if `end_all` takes the supervisor's lock (hangs: the test's timeout fails it), or if only the pid is killed and not the group (the child lives).
- `test_soft_restart_also_ends_groups_close_left_behind`: start a `deaf` `Process` directly, not held in any slot (as a `dying` warm process or an interrupted `_kill` is), so `Supervisor.close()` cannot see it. Call `running._restart(p, args)`. Asserts its group is gone when `execv` is called. Fails if `end_all` reads the supervisor's lists instead of `GROUPS`.
- `test_a_daemon_spawned_while_the_restart_collects_groups_kills_itself`: monkeypatch `supervise.end_all`'s step between taking the snapshot and signalling (wrap the snapshot to spawn a new `deaf` `Process` right after it). Asserts the new process's group is dead within 2 s and its pgid is not in `GROUPS`. Fails if registration does not check `CLOSING` under `GROUPS_LOCK` (lesson-1).
- `test_end_all_waits_once_for_all_groups_not_once_each` (`@pytest.mark.serial`): three `deaf` groups; `end_all(1.0)` returns in under 2.5 s, and all three groups and their children are dead. Fails with a per-group wait (≥ 3 s). A second assert: `end_all(3600)` with one deaf group returns in under 5 s. Fails without the clamp (lesson-4).
- `test_groups_are_forgotten_once_they_end`: an Engine with a daemon, a crash and restart (the existing `kids-crash` mode), then `e.close()`. Wait until the `_kill` threads finish (poll ≤ 5 s); `proc.GROUPS` is then empty. Fails if `killpg` does not remove a gone group (lesson-5).
- `test_a_group_that_cannot_be_signalled_is_dropped_not_retried`: put a pgid in `GROUPS` and monkeypatch `os.killpg` to raise `PermissionError` for it. `end_all(0.5)` returns in under 2 s and the pgid has left `GROUPS`. Fails if `EPERM` is retried until the deadline in a loop that never ends, or is left in the set (lesson-3).
- The existing `tests/test_daemons.py`, `tests/test_watchdog.py`, `tests/test_resilience.py` and `tests/test_runner_and_state.py` pass unchanged. Their engines must reset `proc.CLOSING` between tests. A conftest-free fixture in the new file resets `CLOSING`/`GROUPS` after each test, and `CLOSING` is only ever set by `end_all`, which in production is always followed by an exec.

## Size budget

70 net lines of code outside `tests/` and `docs/` (about 15 in `proc.py`, 40 in `supervise.py`, 10 in `running.py`, docstrings included). An overrun needs a written reason in "Where it stopped".

## Notes from the plan review (answer each)

- Zombies: daemons spawned by the test process stay unreaped zombies after SIGKILL, so os.kill(pid,0)/killpg(pgid,0) still succeed. Define 'dead' in the tests as ESRCH or state Z in /proc/<pid>/stat, or the hard/soft/three-group tests fail on correct code. Say also whether end_all treats a group with only zombies left as gone; otherwise it waits the full (<=3 s) deadline for unreaped dying processes, which is acceptable but must be stated.
- lesson-1 test shows CLOSING is checked, not that check and add are atomic under GROUPS_LOCK. Give end_all a named snapshot helper the test can wrap, and either add a test that pauses inside registration between the check and the add, or state that atomicity rests on the code holding one lock.
- test_groups_are_forgotten_once_they_end should assert this test's own pgids are absent from proc.GROUPS, not that the set is empty; other tests on the same xdist worker can leave entries (lesson-10).
- Use set.discard in both killpg and end_all, since both remove entries. Note in the end_all docstring the small window where a group removed by killpg after the snapshot is still signalled from the snapshot.
- If os.execv itself raises after end_all, CLOSING stays set and every later spawn kills itself. State the behaviour: the process exits, or _restart clears CLOSING and re-raises.
- Confirm runner.kill_all() does not take the Supervisor lock; otherwise the hard-path test hangs for a reason outside this gap (report it, lesson-13).
- Remove the contradiction in the existing-tests bullet (they 'pass unchanged' yet 'must reset proc.CLOSING'); keep only the fixture in the new file resetting CLOSING/GROUPS.

## Where it stopped

Built as defined. All six acceptance tests are in `tests/test_daemons_restart.py` and pass. The size is
70 net lines outside `tests/` and `docs/` (`git diff --numstat main -- ergostat` after round 2: +87 −17, docstrings
included), so no overrun. Round 1's first count (+86 −16) was taken before the merge of main and the later commits, and
round 1's last commit, with the lease fix, was at 88 net lines. See *Round 2* at the end.

**Each test broken (lesson-9).** Each break was made by hand, run, seen to fail, and undone:
- `_restart` not calling `end_all`: the hard and soft tests fail (daemon and child alive at the exec).
- `end_all` signalling the pid (`os.kill`) instead of the group: the hard, soft and three-group tests fail (the
  child lives).
- `end_all` taking each `Supervisor`'s lock (found through `gc`): the hard test fails ("the hard restart hung").
- No clamp: here the ceiling was raised to 6 s rather than removed, so the run cannot hang for an hour and leave
  deaf processes behind. The three-group test fails ("not clamped to 3 s").
- A wait per group: the three-group test fails (3.06 s against 2.5).
- EPERM counted as still present: the EPERM test fails (waited out the deadline).
- An EPERM group left in `GROUPS` (only `sent` removed): the EPERM test fails.
- `killpg` not removing a group: `test_groups_are_forgotten_once_they_end` fails (both pgids kept).
- Registration not checking `CLOSING`: the spawned-while-collecting test fails (the group escapes).

**Answers to the plan review's notes.**
- *Zombies.* In the tests, "dead" is ESRCH, or state `Z` in `/proc/<pid>/stat` (`ps -o stat=` where there is no
  `/proc`). `end_all` treats a group as present while `killpg(pgid, 0)` succeeds. So a group with only unreaped
  processes left is waited for until the shared deadline (≤ 3 s) and then sent SIGKILL, which does no harm. This is
  said in its docstring. In the engine, a daemon's leader is reaped by its own reader thread (`proc.wait()`), so this
  happens only to an orphan whose new parent does not reap it.
  The patched `execv` polls each pid for at most 1 s before it records "dead". The SIGKILL has been sent by then,
  but the process may not yet have been scheduled to die. A daemon that was never sent SIGKILL lives forever, so the
  poll still tells the two cases apart.
- *Atomicity (lesson-1).* `end_all`'s first step is the named helper `supervise.collect()`, which sets `CLOSING` and
  takes the snapshot. The test wraps it to spawn a process right after the snapshot. No test pauses inside
  registration between the check and the add, because that step has no hook short of splitting `Process.__init__`.
  Atomicity rests on the code holding one lock: `CLOSING` is read and the pid added inside one `with GROUPS_LOCK:`
  block in `Process.__init__`, and `collect` sets and snapshots inside the same lock.
- *Forgotten groups.* The test asserts that its own pgids (every start in `starts.log`) are absent from
  `proc.GROUPS`. It does not assert that the set is empty.
- *Removal.* `killpg` uses `GROUPS.discard`. `end_all` uses `GROUPS.difference_update(snapshot)`, the same
  operation for many entries (no `KeyError`). The window in which a group that `killpg` removed after the snapshot is
  still signalled is noted in `end_all`'s docstring.
  One choice wider than item 2 says, taken as the more reversible one (lesson-5): `killpg` removes the group whenever
  it returns, and that includes after it sends SIGKILL, not only when it sees the group gone. A group sent SIGKILL
  cannot outlive it. If the group were kept until the next check, a pgid the OS could reuse would stay in the set.
- *`execv` raising.* `_restart` catches `OSError` from `os.execv`, clears `CLOSING` under `GROUPS_LOCK` and raises
  again, so the supervisor can spawn daemons again in the process that carries on. The test's sentinel is not an
  `OSError`, so in the tests `CLOSING` stays set until the fixture resets it.
- *`runner.kill_all()`.* It takes no `Supervisor` lock: it sets `STOPPING` and SIGKILLs `runner.LIVE`. The hard test
  passes with the supervisor's lock held throughout. It does set the process-wide `runner.STOPPING`, so the new file's
  fixture clears it.
- *Existing tests.* `tests/test_daemons.py`, `test_watchdog.py`, `test_resilience.py` and `test_runner_and_state.py`
  are unchanged. Only the new file's autouse fixture resets `CLOSING` and `GROUPS` (to what was there before the
  test) and `runner.STOPPING`. It also SIGKILLs every group the test started, so a failing test leaves no deaf process
  behind.

**What was run.**
- `tests/test_daemons_restart.py` together with the four existing files, serially: 102 passed.
- `uv run ruff check ergostat tests scripts`: clean.

**What was not run.**
- The full unit suite and the four browser files: left to the factory's watched run, as the instructions say.
- No merge of origin/main: this clone has no `origin` remote ref and reaching the network is not allowed. Local
  `main` (05c6dc9) is the branch's base, so there was nothing on it to merge. The merge and the suites after it are
  still owed (lesson-7).

**The factory's unit run (after the work above).** 1 failed, 1908 passed, 69 skipped, rc 1:
`tests/test_lease_refused_cost.py::test_many_expired_items_with_long_transcripts_cost_about_what_they_did`, on
`etamodel.read: 0.090s, against 0.012s without`. It is left unfixed in this branch, as lesson-13 says:
- The branch changes nothing that the test reaches. `git diff main..HEAD` touches no file under `ergostat/numbers/`,
  `ergostat/leases/` or `ergostat/spec/items.py`. The test and its bounds are unchanged from main. `etamodel.read`
  never touches `proc.GROUPS`, the supervisor or `cli/running.py`.
- Run alone on this branch afterwards, it passes (`1 passed in 0.81s`).
- The comparison is between two timings of a few milliseconds, one taken after the other, under `-n` load. The extra
  cost the test measures is `fold.refused_expiries` reading 300 items from the item index under its lock. That is
  file and lock work, which a busy worker slows unevenly. Nothing this branch's tests leave behind could cause it:
  the run reported `left_behind: 0`, and the `deaf` programs sleep rather than spin and are SIGKILLed by the new
  file's fixture.
- If the failure is a real cost in `refused_expiries` or the item index under load, and not a timing flake, it
  needs its own gap. I could not profile it here: this session was only allowed to run pytest, so no ad hoc
  script could be run.

**The factory's second unit run.** 1 failed, 1908 passed, 69 skipped, rc 1:
`tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`. A lease was still held after
`second.close()`. In round 1 a fix was written into this branch, outside this gap's files
(`ergostat/leases/dispatch.py`, `ergostat/spec/engine.py`). The test has no daemons, and the race is on main as well.
**That fix has been taken out again in round 2** (see *Round 2*). What follows is kept as the record of what round 1
did and why the review refused it.
- *The race.* The test closes the engine as soon as it sees a new lease. That run could be between
  `Dispatch.take` writing `lease.taken` and spawning its process. (1) `take` added the run to `Engine.running` only
  after the event was written and folded, so `close()` could find `running` empty and return at once. (2)
  `runner.kill_all()` kills only what is in `runner.LIVE`. A run that spawned after it was not killed: `sleep 30`
  outlived `close()`, and its lease stayed held (the holder in the failure is that run's id).
- *The fix (lesson-1, lesson-6).* `take` checks `stop` and adds the run to `running` under `Engine.lock` before
  writing the lease. It removes the run again if the fold refuses the lease or the write raises. `close()` reads
  `running` under the same lock, so a lease is either never taken after `stop` or waited for. `run_block` checks
  `runner.STOPPING` after `LIVE.add(proc)` and kills the new group if it is set. The add comes before the check, and
  `kill_all` sets the flag before it reads `LIVE`, so either `kill_all` sees the process or the process sees the flag.
  The run then ends as "stopped with ergostat", and `finish` gives the lease back uncounted.
- *Not run.* Round 1's session was denied the shell, so the fix was never run (not the failing test, not ruff, not
  the suites). The earlier sentence here said it "has not been committed". That was wrong: the factory committed it,
  untested, as 95af273 ("work the session left uncommitted").

**Round 2 (answers to the review, every finding).**
- *Lease fix outside the gap (lesson-13; blocking).* Removed. `ergostat/leases/dispatch.py` and
  `ergostat/spec/engine.py` are back to main's text (`git diff main -- ergostat/leases/dispatch.py
  ergostat/spec/engine.py` is empty). The race is now its own entry in `docs/GAPS.md` (*Runtime, scale and latency*:
  "A lease taken while the engine closes outlives the close"). That entry names
  `test_leases_survive_a_restart_the_fold_is_the_truth` as the reason, and it gives both halves of the race and the
  constraint below. The review (code-health-1) pointed to a parked `lease-shutdown-race` gap, but this clone has no
  file or GAPS entry for one (only a mention in `docs/roadmap/overnight/main-broken.md`), so the entry is new. If the
  factory already tracks that gap elsewhere, the two should be merged.
- *Notes that did not match the branch (lesson-8; blocking).* Corrected above. The lease fix was committed untested in
  95af273, not left uncommitted. The size line now gives the measured count. Removing the lease fix brought the diff to
  +89 −17 (72 net). Two lines were then saved without changing behaviour: the `os.execv` call in `_restart` is back on
  main's two lines, and `supervise._signal` is one line shorter. That gives 70 net lines, inside the budget.
- *Process-wide `runner.STOPPING` in `run_block` (lesson-9, lesson-6).* That check went out with the lease fix. The
  GAPS entry records the constraint: a fix there must not key on the process-wide flag, and needs its own test.
- *Run in round 2, one file at a time (`uv run python -m pytest -q <file>`):* `tests/test_daemons_restart.py` 6
  passed, `tests/test_daemons.py` 26 passed, `tests/test_leases.py` 20 passed (on main's lease code; the race is a
  flake there, not seen in this run), `tests/test_watchdog.py` 3 passed, `tests/test_resilience.py` 24 passed,
  `tests/test_runner_and_state.py` 43 passed. `uv run ruff check ergostat tests scripts` is clean.
- *Not run in round 2:* the full unit suite and the four browser files (left to the factory's watched run). The
  break-each-test checks (lesson-9) were not run again: the code they guard is the same as in round 1, apart from
  the two lines reflowed above. There was no merge of origin/main: this clone has no `origin` ref, and
  local `main` (8eb0fc0) is already merged in (9974606).
