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
