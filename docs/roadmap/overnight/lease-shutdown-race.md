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

### Round 2 (review lease-shutdown-race-1)

- **Blocking: the 30 loaded `-n 8` runs. Still not run, and the claim is narrowed here.** This session's harness again
  refused `scripts/suite_watch.py` and any `-n 8` pytest. I did not get around that, for example with a test that
  starts workers of its own. So the branch does **not** claim that the restart test no longer flakes under load. It
  claims this much: the race named in the definition (a take or a run start that lands after the stop) is closed, and
  each part that closes it has a test that fails with that part disabled. The DoD's last acceptance line (30 loaded
  runs) is still open. The factory's watched run must make it, and it stays a blocker for "done" until it does.
- **Another possible cause of the restart test's flake.** The test sleeps a fixed 0.6 s and then asserts that the
  second engine still keeps the first engine's lease (TTL 1.5 s, grace 1 s). On a loaded machine that sleep can
  stretch past the second engine's two watchdog looks, so the lease expires first. That is a fixed sleep in the test
  (lesson-10), not this race. If the watched run still shows the test flaking, look there first. It is left alone
  here because changing the test's timing would hide what the loaded run is meant to show.
- **The hang in round 1's unit run.** It is now shown that the round-1 check (`runner.STOPPING`) killed runs started
  by another engine after any engine's close. The new `test_another_engines_run_survives_this_engines_close` fails
  with that check put back (the run is killed and never reaches `done`) and passes with `self.stop`. A test waiting
  for such a run waits until it times out, which fits round 1's hang. That the factory's hang was exactly this is
  likely but still not proven: only a watched run can show it.
- **Non-blocking findings, each answered:**
  - *No tests for the `run_block` kill and `_work`'s check.* There are now three:
    `test_a_run_whose_process_starts_as_the_engine_stops_is_killed_and_given_back` (the stop is set as the process
    starts), `test_a_run_whose_thread_starts_after_the_stop_is_not_started` (the stop is set after the take, before
    its thread runs) and `test_another_engines_run_survives_this_engines_close`. Each was broken on purpose and seen
    to fail: the `run_block` check removed fails the first; the check made `runner.STOPPING` again fails the first
    and the third; `_work`'s check removed fails the second.
  - *The restart test's no-op `finish`.* The test stands in for an engine that dies: it never calls `close`, so
    `give_back` is never in play there, and the no-op only keeps the dying engine from ending its lease. A comment
    there now says so. `give_back` itself is covered by `test_a_take_racing_the_stop_is_given_back_uncounted`.
  - *`finish` running under the dispatcher's lock.* Narrowed as the review suggested: `_work` and `give_back` now only
    claim the lease (check `going` and pop it) under the lock, and call `finish` outside it. A claimed lease is still
    held in the fold until `finish` writes its end, so a look in between still counts it and never takes the item.
- **The `test_messages` then `test_run_costs` failure noted in round 1** is unchanged and still unrelated (lesson-13).
- **Size:** 35 net lines outside `tests/` and `docs/`, of the 120 budget.
- **Ran serially:** `test_leases` (25 passed), `test_lease_kill`, `test_leased_workspaces`, `test_daemons` (64 passed
  together), and `test_streamed_output`, `test_runner_and_state`, `test_resilience`, `test_watchdog`,
  `test_reload_in_place` (91 passed). Ruff is clean. origin/main: there is no remote in this worktree, and local `main`
  is already merged (9427544).
