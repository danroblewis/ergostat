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
