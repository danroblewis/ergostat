# lease-shutdown-race: a run started as ergostat stops never keeps its lease

depends-on: []

Branch `lease-shutdown-race`, from main. Found by grooming: `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth`
flakes on main because a run started while the engine is stopping keeps its lease (the take and the stop race in
`ergostat/leases/dispatch.py`'s take and `ergostat/spec/engine.py`'s shutdown). Any gap's unit run can hit it; it held
back inbox-dismiss, whose round 3 wrote a fix and two tests for it on `factory/inbox-dismiss` and was told (rightly) to
move them into their own gap. Start from that fix (in the drop as `factory/inbox-dismiss`, round 3), lifted out alone.

## Definition of done

No lease is taken once the engine has begun stopping, and a take that raced the stop is given back (uncounted) before
the engine exits, so after a restart the fold is the truth: no item is left leased by a run that never ran. The fix
holds under load: the test passes 30 runs of `-n 8` with the CPU loaded, and the restart test no longer flakes.

## Acceptance tests

- `tests/test_leases.py::test_no_lease_is_taken_once_the_engine_is_stopping`
- `tests/test_leases.py::test_a_take_racing_the_stop_is_given_back_uncounted`
- `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` (no longer flaky: 30 loaded runs)

## Size budget

120 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1, built; one acceptance check not run here (below).

- **The drop was not there.** No `factory/inbox-dismiss` branch or drop is reachable from this worktree, so the fix was
  written fresh from the code and the inbox-dismiss reviews' notes, not lifted from round 3.
- **The race.** `close()` set `stop`, killed the live runs, and waited for `running`; a `tick` already past its stop
  check could still write a take and start a run afterwards, which nothing killed and nothing waited for (the take was
  added to `running` only after its write). The restart test's `second.close()` then left that item leased.
- **The fix** (35 net lines, of 120):
  - `dispatch.take`: under the engine's lock (which `close` now sets `stop` under), it checks `stop` and registers
    the run in `running` *before* writing the take, so `close` waits for every take that got past the check; after the
    write it checks `stop` again, and a take that raced the stop is given back (`nack`, "stopped with ergostat",
    uncounted) before any run starts.
  - `dispatch._work`: a run whose thread starts after the stop is not started; its lease is given back uncounted.
  - `engine.run_block`: a process started once this engine is stopping (`stop` set, which `close` does before its
    `kill_all`) is killed at once (it is added to `LIVE` before the check, so either `kill_all` or this check sees it).
  - `dispatch.give_back`, called by `close` after its five-second wait: any lease still going here is given back
    uncounted before `ergostat.stopped` is written. `_work`'s own ending and `give_back` both hold the dispatcher's
    lock and end a lease only while it is still in `going` under the same run, so it is ended once.
  - SPEC §9.5 says so.
- **Tests.** Both new tests were seen to fail with each part they guard disabled: the stop check before the take
  (no-lease test), the check after the write, and `close`'s `give_back` (racing test). The `run_block` kill and the
  `_work` check have no test of their own (each is a few lines; their window is a thread switch).
- **Not run here: the 30 loaded `-n 8` runs.** This session was not allowed to start parallel pytest, CPU-load
  processes or a repeat loop (the factory runs the suites after the implementor). Run serially: `tests/test_leases.py`
  (22 passed), `tests/test_lease_kill.py`, `tests/test_leased_workspaces.py`, `tests/test_daemons.py` all pass; ruff
  clean. The loaded 30-run check of the restart test is still to be done by the factory's watched run.
- **Decision taken alone (reversible):** `finish`'s existing "stopping" label for any non-zero exit while the engine
  closes (review inbox-dismiss-1's note) is left as it is on main: narrowing it is outside this gap.
- No origin remote in this worktree; the branch is made from local `main`, with nothing newer to merge in.

### After the factory's unit run (failed)

- **What the tail showed.** The factory's `unit` run stopped at 73% with no failure line and no summary, so the
  output does not name the test. It looks like a hang, or the watchdog killing the run, not an assertion.
- **What was changed.** `run_block` killed a newly started run when `runner.STOPPING` was set. That flag is
  process-wide: any engine's `close` (and `kill_all`) sets it, and only an engine's start clears it. So once any
  engine in a pytest worker had closed (or a test called `kill_all`), every run that a *different*, unstarted engine
  began was killed as it started. A test waiting for such a run to finish could wait to its timeout or hang. The check
  is now this engine's own `stop`, which `close` sets (under its lock) before its `kill_all`, so the window it guards is
  still covered. One line changed.
- **Not shown to be the cause.** Run serially, the suites did not reproduce the hang with either check. Under `-n 8`
  the factory's watched run is still the test of this fix.
- **Unrelated, found while looking:** `tests/test_messages.py` followed by `tests/test_run_costs.py` in one process fails
  `test_fifty_short_runs_at_once_share_one_sampler_and_its_cost_stays_small` (`SAMPLER.stats()["running"]` still true),
  with or without this round's change. `test_messages` takes no lease and closes no engine, so it does not touch what
  this branch changed. It could not be checked against `main` here (no second worktree allowed). Reported, not fixed
  (lesson-13).
- Ran serially: `test_leases`, `test_lease_kill`, `test_leased_workspaces`, `test_streamed_output`,
  `test_runner_and_state`, `test_daemons`, `test_resilience`, `test_watchdog`, `test_reload_in_place` (152 passed);
  ruff clean.
