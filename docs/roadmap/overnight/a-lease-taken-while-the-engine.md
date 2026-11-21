# a-lease-taken-while-the-engine: a lease taken or a run spawned while this engine closes is given back or killed before `close()` returns, keyed on this engine's own stop
depends-on: []

## Definition of done

The race is on main today. `Dispatcher.take` (`ergostat/leases/dispatch.py`) writes and folds `lease.taken` before it adds the run to `Engine.running`. So `Engine.close()` (`ergostat/spec/engine.py`) can find `running` empty and return while a take is still under way. Also, a process that `run_block` adds to `runner.LIVE` after `close()`'s `kill_all()` is never killed. The parked branch `factory/lease-shutdown-race` has a 53-line fix for both. It was parked only because the 30 loaded runs it promised could not be run. The implementor may lift that fix. When this branch is done:

1. **No take after the stop.** Once `close()` has begun (this engine's `stop` is set), no new `lease.taken` is written. A take that got past its stop check is already counted in `running` before its write, so `close()` waits for it. A take whose write raced the stop is given back uncounted (`stopped with ergostat`) and starts no run. The check, the registration in `running` and the stop that `close()` sets are all done under one lock (lesson-1). `close()` never blocks forever on that lock.
2. **No run outlives the close.** A process that `run_block` starts while this engine is stopping is killed (its process group), whether it was added to `LIVE` before or after `kill_all()`. The test for this keys on **this engine's** `stop`, never on `runner.STOPPING`. A second engine in the same process keeps its run.
3. **Nothing left held.** Before `close()` records `ergostat.stopped`, every lease this engine still holds is given back uncounted, and each is ended once (no double ack/nack with `_work`'s own ending).
4. `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` passes. Its fixed `sleep(0.6)` is replaced by a wait on the record (lesson-10).
5. SPEC §9.5 (the "A run stopped with ergostat" sentence, around line 2164) also says that a lease taken, or a run started, while the engine stops is given back uncounted or killed before it exits. `docs/GAPS.md` gets a *Done recently* line for this gap (on main the entry exists only in the factory's brief).
6. **What done does not require.** Repeated loaded runs are not part of done: the deterministic window tests below replace them. Done does require the house-rule suites, run once each and reported honestly (lesson-13 for any unrelated failure).

## Relation to other work

- `lease-shutdown-race` (parked, not merged): this gap replaces it. Its code may be reused. Its 30-loaded-runs line is dropped.
- `pool-control` (ready): it depends on `gap/lease-shutdown-race`, and this gap is what fills that dependency.
- `external-event-logs` (fix): it also touches `ergostat/spec/engine.py`. This branch changes only `close()` and `run_block`'s spawn, and merges main before review.
- `daemons-left-over` (building): it uses the daemon path's `run_item`, which this branch does not change.

## Files to touch

- `ergostat/leases/dispatch.py`
- `ergostat/spec/engine.py`
- `tests/test_leases.py`
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks

- lesson-1: the stop check and the registration in `running` are not done under the lock `close()` sets `stop` under, which leaves a new gap between the check and the write.
- lesson-6: the run in the window gets a "done" answer but its process keeps running. Or the kill keys on the process-wide `STOPPING` and kills another engine's run.
- lesson-9: a window test that never actually puts the stop inside the window, so it passes on main as well.

## Acceptance tests

- `tests/test_leases.py::test_no_lease_is_taken_once_the_engine_is_stopping`: once `stop` is set by `close()`, a dispatcher look writes no `lease.taken`. It fails on main.
- `tests/test_leases.py::test_a_take_racing_the_stop_is_given_back_uncounted`: the events write inside `take` is monkeypatched to run `close()`'s stop in the gap. The item ends unheld, its history says `stopped with ergostat` with `counted: False`, and no run started. It fails on main.
- `tests/test_leases.py::test_a_run_spawned_after_kill_all_is_killed`: the spawn in `run_block` is monkeypatched so the engine's stop and `kill_all()` happen just after the process starts (a `sleep 30`). The process group is gone within a few seconds, and the lease is given back uncounted. It fails on main.
- `tests/test_leases.py::test_one_engine_closing_does_not_kill_another_engines_run`: two engines in one process. One closes while the other's run is starting (with `STOPPING` set by the first engine's `kill_all`). The second engine's run is still alive and still holds its lease. It fails if the kill keys on `runner.STOPPING`.
- `tests/test_leases.py::test_close_gives_back_every_lease_still_going`: a run whose `finish` is stubbed out, so its lease would stay held. After `close()` the lease is ended exactly once, uncounted, before `ergostat.stopped` by `seq`.
- `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`: as on main, with its fixed sleep replaced by a wait on the record.

The report says, for each new test, which part of the fix was disabled to watch it fail.

## Size budget

80 net lines

## Notes from the plan review (answer each)

- runner.kill_all() (ergostat/runner.py:55-58), which close() calls at engine.py:1744, kills every process in LIVE across all engines. A second engine's run that is in LIVE before the first engine's kill_all() is killed on main and on this branch alike, so 'a second engine in the same process keeps its run' only holds for a run spawned after kill_all(). Either have close() kill only this engine's own self.live and leave STOPPING to the process exit, or narrow done item 2, the SPEC sentence and test_one_engine_closing_does_not_kill_another_engines_run to a run spawned after kill_all(), and say which you chose. Also note that STOPPING stays set, so engine.py:975 labels the surviving engine's non-zero exit STOPPED_WITH_US.
- Done item 3: close()'s give-back of the leases still held and _work's finish() (dispatch.py:260-280) both read the record and then write lease.ended, with no shared lock. A run finishing while close() gives back its lease can end it twice. Do both under one lock (Dispatcher.lock), re-reading inside it, and add a test that puts finish inside close()'s gap, not only one where finish is stubbed out.
- test_a_take_racing_the_stop_is_given_back_uncounted: once a take is counted in running before its write, a patched events.add that calls the real close() makes close() wait its whole 5s deadline on that same take (engine.py:1746-1748), and ergostat.stopped lands before the give-back. Have the patch set the stop (under the engine lock) and call kill_all(), then check that the give-back comes before any later close() writes ergostat.stopped, by seq.
- The 80 net lines are tight: the parked fix is 53 lines, plus five new window tests and the SPEC and GAPS lines. Check early whether tests count against the budget. If they do, share one fixture for the two-engine and spawn-window tests rather than cutting the window tests.
- The daemon path (engine.py:938-940, daemons.run_item) is not covered by the spawn-side kill. Say in SPEC §9.5 that a daemon's item is stopped by daemons.close(), or narrow 'a run started while the engine stops is killed' to processes run_block spawns itself.

## Where it stopped

Built, round 1. Nothing in the definition is left undone. Here are the choices made, with nobody to ask (each the more reversible one):

- **The parked fix was not lifted.** `factory/lease-shutdown-race` is not in this clone, so the fix was written fresh. It is 37 net lines of code outside `tests/` and `docs/` (`dispatch.py` +30, `engine.py` +7), within the 80-line budget.
- **Done item 2 is narrowed, not widened** (plan review note 1). `close()` still calls `runner.kill_all()`. So a second engine's run that is **already in `runner.LIVE`** when the first engine kills its runs is killed with them, on main and here alike. What this branch guarantees is the spawn side: a process `run_block` starts once **this** engine's `stop` is set is killed. The check is made under `Engine.lock`, where `close()` sets the stop, and keys on that stop. A run another engine starts after the first engine's `kill_all()` goes on. Making `close()` kill only its own `self.live` would change what the process-wide kill covers for every other user of `LIVE` (the `Runner`), so that change is left to its own gap. `STOPPING` stays set after one engine closes. A surviving engine's run that then exits non-zero is still labelled `stopped with ergostat` (`engine.py`, the `note =` line). SPEC §9.5 says both.
- **Done item 3, ended once** (plan review note 2). `Dispatcher.finish` reads the record and writes `lease.ended` under `Dispatcher.lock`. `close()`'s `give_back()` goes through the same `finish`. `Dispatcher.mine` (run → block, item, fence) holds the leases this engine took and has not ended; `finish` drops an entry once it has ended its lease or found it already ended. There is one more test than the definition lists: `test_a_runs_own_end_inside_close_s_give_back_ends_it_once`. It starts the run's own `finish` in the gap between the give-back's read and its write.
- **The racing-take test** (note 3) sets the stop under `Engine.lock` and calls `kill_all()` inside the patched `lease.taken` write. It does not call `close()` there. Only afterwards does it call the real `close()`, and it checks by `seq` that the give-back comes before `ergostat.stopped`.
- **"Finish stubbed out"** (test 5) is a `finish` that raises on its first call (the run's own end), which `_work` logs as "the watchdog ends it later". It cannot be a stub that does nothing on every call, because `close()` ends the lease through that same `finish`.
- **The daemon path** (note 5): SPEC §9.5 says a daemon's item is stopped by the daemon's own close (§9.7). The spawn-side kill covers only the processes `run_block` starts itself.
- **`close()` takes `Engine.lock` with a 5 s timeout** to set the stop. If the lock is not free by then, it sets the stop anyway, so it never blocks forever. A take and a spawn hold the lock only for a set operation, never across a write.
- **The restart test** no longer sleeps for a fixed 0.6 s. It waits for the expiry record, then checks by `seq` that before the expiry only the first engine's take exists and no lease ended.
- **GAPS.md**: on main the entry was in the open list, under *Engine*, not only in the brief. It was moved to *Done recently*.

How each new test was watched failing, with one part of the fix disabled at a time:
- `test_no_lease_is_taken_once_the_engine_is_stopping`: the take's stop check disabled. A `lease.taken` was written.
- `test_a_take_racing_the_stop_is_given_back_uncounted`: the re-check after the write disabled. An `agent.started` was recorded, so a run started.
- `test_a_run_spawned_after_kill_all_is_killed`: the spawn-side kill disabled. The `sleep 30` group was still alive after 5 s.
- `test_one_engine_closing_does_not_kill_another_engines_run`: the spawn-side kill keyed on `runner.STOPPING`. The other engine's run died.
- `test_close_gives_back_every_lease_still_going`: `give_back()` removed from `close()`. No `lease.ended` was recorded.
- `test_a_runs_own_end_inside_close_s_give_back_ends_it_once`: `finish`'s lock replaced by a fresh lock. Two `lease.ended` were recorded.

Tests run (one file group at a time, not under the factory's watchdog):
- `tests/test_leases.py`: 29 passed.
- `test_lease_kill`, `test_lease_refused_cost`, `test_leased_workspaces`: 14 passed.
- `test_daemons`, `test_daemons_restart`, `test_warm`: 53 passed.
- `test_spec_engine`, `test_runner_and_state`, `test_ticket_factory_daemons`, `test_workspaces`: 68 passed.
- ruff: clean.

Not run here: the whole unit suite and the four browser files. The factory runs those under its watchdog. There is no `origin` remote in this clone; local `main` is already merged in.

After the factory's `unit` run failed: its tail ends after 12 tests (the slow tests at the head of each worker) with no failing test, summary or traceback, so the run was cut off rather than failing on a named test. Nothing here could be matched to it, and no code was changed:
- The whole unit suite, run serially in four file groups (`tests/test_[a-e]*`, `[f-l]`, `[m-r]`, `[s-z]`): 2,031 passed, 69 skipped, no failure.
- Under `-n 8 --dist worksteal`: every `slow` test (41 passed), and `test_leases`, `test_lease_kill`, `test_daemons`, `test_streamed_output`, `test_triggers2` together (95 passed).
- Every new wait in the fix is bounded: `close()` takes `Engine.lock` with a 5 s timeout, and the spawn-side kill and the take hold that lock only for set operations. `Dispatcher.lock` is now also held by `finish`, but the code under it waits on nothing that needs a run to end.
The factory should run `unit` again and keep its full output. If it stops early again, the test it stops in is what to look at.
