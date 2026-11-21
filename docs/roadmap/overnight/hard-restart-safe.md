# hard-restart-safe: An engine's hard restart never leaves two runs of one item or spends an attempt

depends-on: []

Audit 2026-11-21, reproduced on real engines. (1) A regression from `f2dba020`: `_restart` waits up to 3 s in `end_all` (`ergostat/cli/running.py`) but the hard path never sets `engine.stop`, so the dispatcher keeps leasing. A run started in that window survives the `exec`; the new engine expires its lease without killing it and starts a second run. Two live runs of one item in 3 of 3 attempts, so a side effect such as a push can happen twice. (2) An item held during the engine's own hard restart spends an attempt: with `attempts: 1` it becomes a dead letter, while SPEC says such items are taken again.

## Definition of done
- Dispatch is closed before `end_all`, and any run spawned once stopping has begun is killed.
- A lease expired because its holder belonged to a previous engine process is uncounted.

## Files to touch
`ergostat/cli/running.py`, `ergostat/leases/dispatch.py`, `ergostat/spec/engine.py`, `tests/test_resilience.py`.

## Risks
- lesson-1: closing dispatch and taking a lease are one step.
- lesson-9: the test uses a real engine and a daemon that ignores SIGTERM.

## Acceptance tests
- `tests/test_resilience.py::test_a_hard_restart_never_leaves_two_runs_of_one_item`
- `tests/test_resilience.py::test_a_hard_restart_spends_no_attempt`

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Built, round 1; 19 net lines of code (running.py +7, dispatch.py +7, engine.py +4, fold.py +1).

- **Dispatch closed first.** `Engine.shut(wait)` sets the stop under `Engine.lock`, the lock a take checks it under
  (lesson-1: the check and the count of `take` are one step under that lock). `close()` now calls it.
  `_restart_hard` calls it (waiting at most 1 s for the lock) before `kill_all` and `end_all`. A take past its check
  sees the stop again after its write and gives the item back; a run whose process starts after the stop is killed
  by the existing check after `LIVE.add`. `cmd_run` passes the engine to every hard restart: the watchdog's, the run
  loop's on a wedge, and the start-up watchdog's once the engine exists.
- **Uncounted expiry.** The dispatcher keeps `ours`: the runs it took whose leases have not ended. An expiry of a
  lease whose holder is not among them is written with `count: false`. Only the dispatcher writes `lease.taken`, so
  any other holder is a previous engine's.
- **Outside the files list:** `ergostat/leases/fold.py` (one line). The fold counted every expiry whatever its data
  said, so `count: false` needed it. This is the smallest reversible place for the change.
- **Choices made without an answer (most reversible):** the previous engine is told apart in memory, not recorded,
  so the event format gains only `count`. A lease from a previous engine that crashed for any reason (kill -9, power
  loss) is also uncounted. An item that crashes the engine every time it runs would therefore never become a dead
  letter. That is SPEC's "such items are taken again", but the owner may want a cap.
- **Not covered:** a run whose process is being forked at the very moment of the exec (SPEC says so).
- **Tests broken to fail:** with the hard path's `shut` disabled, test 1 found runs of job/2 and of job/1 (taken
  again) alive at the exec. With `counted = True`, or with the fold line reverted, test 2 found a dead letter.
- No `origin/main` ref in this clone and `main` is not ahead of the branch: nothing to merge.
