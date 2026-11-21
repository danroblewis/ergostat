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

### Round 3 (review lease-shutdown-race-2)

- **Blocking: the restart test's fixed sleep. Fixed.** `test_leases_survive_a_restart_the_fold_is_the_truth` no
  longer sleeps 0.6 s and then reads the item. It waits for the expiry, then checks the record in `seq` order, which
  holds however late a look comes (lesson-2, lesson-10):
  - the first engine's lease ended only by its expiry (`how == "expired"`, the dead run's id), on the `expires` it was
    taken with: the new engine read the lease and kept it;
  - every take by the new engine has a higher `seq` than that expiry: the lease held counted against the pool until
    it expired. This cannot pass by luck under load. The new engine's first pass looks before it takes, and that look
    only marks the lease overdue. The expiry needs a second look a grace later, so a take that ignored the held lease
    would land before the expiry.
  - Seen to fail (lesson-9): with the pool count ignoring held leases (`mine = set()` in `tick`), the test fails on
    the pool assertion. With the code restored, it passes.
  - The TTL and timeouts were not raised. The only waits left (`wait_for`, up to 10 s and 5 s) are ceilings on events
    that must come, not sleeps that decide the result.
- **Blocking: the 30 loaded `-n 8` runs. Still not run, and still a blocker for "done".** In this session the
  harness refused `scripts/suite_watch.py -- pytest -n 8` again, even a single run. I did not get around that. The
  DoD's last acceptance line can only be met by the factory's watched run, which should record its counts here:
  `suite_watch.py -- pytest -n 8 tests/test_leases.py`, 30 times with the CPU loaded. I make no claim that the test
  no longer flakes under load. What changed: the one timing-dependent read it had (the fixed sleep) is gone, so
  the expiry and pool assertions no longer depend on timing.
- **Round 2's non-blocking findings, each answered (lesson-12):**
  - *SPEC §9.5's "no item is left leased" (lesson-8).* Narrowed: a lease that could not be given back (the write
    failed, or ergostat was killed) is expired by the next engine's watchdog on its TTL. The restart test covers
    that path.
  - *`take`'s `running.discard` outside `e.lock`.* All three discards in `take` are now under the engine's lock.
  - *`give_back` after `close`'s wait ends the lease of a run that may still be going.* A comment at the call in
    `engine.close` now says why this is safe for a new engine in the same process: once the lease ended, the fence
    refuses that run's later lines about the item. No code change.
- **Size:** 41 net lines outside `tests/` and `docs/` (comments included), of the 120 budget.
- **Ran serially:** `test_leases` (25 passed), `test_lease_kill`, `test_leased_workspaces`, `test_daemons` (39
  passed). Ruff is clean. There is no remote, and local `main` is already merged (485cc0e), so there is nothing newer
  to merge.

### After round 3's unit run (failed)

- **What the tail showed: nothing to go on.** The output stops right after `uv`'s install line. No test progress, no
  failure and no summary were printed, so it names no test. Collection is fine (1958 tests, run here). The likeliest
  reading is a run killed while its output was still buffered: a hang, as in round 1.
- **What could hang that this branch added.** Two waits with no limit, both in `close`: round 1 made it set `stop`
  under the engine's lock (`with self.lock`), and `give_back` takes the dispatcher's lock. The watchdog is written
  for an engine whose lock is held for good (`new_pool` takes it with a timeout, `running.py` avoids `close` on a
  wedged engine), and a look holds the dispatcher's lock while it takes. So a pass or a look wedged in any test made
  `close` (and so the test's teardown) wait for good, where on main `close` never waited on either lock.
- **What changed (code).** `close` waits for the engine's lock at most `Engine.lock_wait` (5 s), and sets `stop`
  either way. `give_back` does the same for the dispatcher's lock; when it times out it says so and leaves the
  leases to the next engine's watchdog, as SPEC §9.5 already says. The race stays closed: a take must hold the
  engine's lock to pass its stop check, so a take queued behind a wedged holder sees the stop once it gets the lock.
- **Test.** `test_close_returns_when_its_locks_are_held_for_good`: a thread holds both locks for good. `close`
  returns, `stop` is set, `ergostat.stopped` is written, and a look after the wedge lets go takes nothing. Seen to
  fail (lesson-9) with `close` waiting on the engine's lock with no limit, and again with `give_back` waiting on the
  dispatcher's lock with no limit.
- **Not shown to be the factory's cause.** No hang was reproduced here, serially. The suite was not run whole: the
  rules say it runs through the slot script under `suite_watch.py`, and that is the factory's run. The 30 loaded
  `-n 8` runs of the restart test are still not run, and are still a blocker for "done" (see Round 3).
- **Size:** 53 net lines outside `tests/` and `docs/` (comments included), of the 120 budget.
- **Ran serially:** `test_leases` (26 passed); `test_lease_kill`, `test_leased_workspaces`, `test_daemons`,
  `test_watchdog`, `test_resilience`, `test_reload_in_place`, `test_runner_and_state`, `test_streamed_output` (130
  passed). Ruff is clean.

### Round 4 (the findings carried from review lease-shutdown-race-2)

- **The restart test's fixed sleep: already fixed in round 3, nothing new.** Checked again: no `sleep` is left in
  `test_leases_survive_a_restart_the_fold_is_the_truth`. It judges the record by `seq` (see Round 3), and it was
  seen to fail with the pool count broken.
- **The 30 loaded `-n 8` runs: still not run. They still block "done", and this round cannot clear them.** This
  session's harness refused `scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py` again, even one run, and also
  refused a serial loop that repeats the restart test. I did not get around that. No code changed this round, because
  the finding asks for a measurement, not a fix. Writing more code to stand in for the measurement would just be the
  wider claim lesson-8 warns against. **What the factory must do:** run `suite_watch.py -- pytest -n 8
  tests/test_leases.py` 30 times with the CPU loaded, and record the pass/fail counts here. If that is never allowed
  from an implementor's session, the gap should be parked with this line as the one thing left. Each implementor
  round can only repeat this same answer.
- **Ran:** `tests/test_leases.py` serially (26 passed); ruff is clean. There is no remote and nothing newer on local
  `main` to merge.

### After round 4's unit run (failed again; no cause found, no code changed)

- **What the tail showed.** The run stopped at 80% with no failure line, and with no `suite_watch` line either (no
  "past the limits", no closing JSON line). So it was not the watcher's own thread or memory kill. The watcher itself
  was stopped from outside, most likely by an outer timeout. Round 1 stopped at 73%, and round 3 before its first
  test, which no change in this branch can cause (collection is fine).
- **A reading of the stall.** Under xdist, `conftest.py` makes a `serial` test (all of `test_watchdog`, one in
  `test_daemons`, `test_parallel_runs`, `test_notify`, the heavy diagram ones) hold the run's lock alone. One of them
  hanging, or running very slowly on a loaded machine, holds back every worker. That fits a stall at any percentage
  better than one test hanging on its own worker. Nothing here shows which test it was.
- **What was looked for, and not found.** I went through every lock and wait this branch adds:
  - The lock order is unchanged from main. `take` holds the dispatcher's lock and then takes the engine's, as main
    did. Nothing in `ergostat/` takes the dispatcher's lock while holding the engine's (`dispatch` is only touched
    from `engine.py`, plus `due_now` in `daemons/supervise.py`, which takes no lock).
  - Both of `close`'s new waits have a limit (`lock_wait`).
  - `give_back` runs inside `take` only on the race path. The locks are RLocks, so taking one again in the same
    thread does not deadlock.
  - The `run_block` kill applies only to this engine's own `stop`. No test outside `test_leases` sets an engine's
    `stop` and then starts a run on it.
  - `runner.STOPPING` is cleared before every test by `conftest._not_stopping`.
- **Run here, one file at a time, all passed:** `test_notify` + `test_parallel_runs` (serial-marked), `test_spec_engine`,
  `test_ticket_factory_daemons`, `test_triggers2` + `test_triggers3`, `test_reload_safety` + `test_repair2` +
  `test_workspaces`, `test_reload_soak` + `test_calls` + `test_messages`. This session's harness refused a loop over
  every test file, even one at a time, and refused any `-n 8` run, so the whole suite was not run here.
- **Decision taken alone (reversible).** No code change this round. Changing code without a cause would hide what
  the next watched run could show. What is needed is a watched unit run that names the stuck test: for example
  `pytest -n 8 -o faulthandler_timeout=300`, which dumps every thread's stack for a test past 300 s. It is also worth
  running main's unit suite on the same machine, to see whether main stalls the same way.
- **Still open, as before:** the 30 loaded `-n 8` runs of the restart test (the DoD's last acceptance line), and a
  green unit run. The gap is not done.

## Where it stopped

Parked by the factory (implementor, 2026-11-20 14:35).

Its fast suites failed 2 times (the kill rule); the last: the fast suites failed (unit: tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder).

```
<module 'factory_fac' from '/work/dev/bin/fac.py'>, <module 'factory_sessions' from '/work/dev/bin/sessions.py'>, {'p...ntainer_mounts_only0/live'}, 'ai': {'mode': 'container', 'implementor_model': 'opus', 'implementor_session_usd': 5.0}})

    def test_the_container_mounts_only_the_sessions_own_folder(tmp_path, mods):
        fac, sessions, cfg = mods
        agents = module("agents")
        keep = sessions.Session(cfg, "reviewer", None)
        args = agents.run_args({**cfg, "ai": {"reviewer_model": "opus", "reviewer_session_usd": 1}}, "reviewer",
                               tmp_path / "work", "n", keep)
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        assert mounts == [f"{tmp_path / 'work'}:/work:ro", f"{keep.raw}:/home/dev/.claude/projects"]
>       assert not any(str(Path.home()) in m for m in mounts) and "run" not in keep.raw.parts
E       assert (not True)
E        +  where True = any(<generator object test_the_container_mounts_only_the_sessions_own_folder.<locals>.<genexpr> at 0xffffa2fd6ea0>)

/work/tests/test_factory_sessions.py:179: AssertionError
=========================== short test summary info ============================
FAILED tests/test_factory_sessions.py::test_the_container_mounts_only_the_sessions_own_folder
1 failed, 1895 passed, 69 skipped in 257.86s (0:04:17)
{"rc": 1, "wall_s": 258.9, "peak": {"threads": 356, "rss_mb": 1542.5, "procs": 126, "worker_mb": 615.6}, "killed": null, "workers_killed": 0, "left_behind": 0}

```

### Round 5 (after the park)

- **The parking failure is not this branch's, and main has already fixed it.** It was
  `test_the_container_mounts_only_the_sessions_own_folder`. That test looked for the home folder's path anywhere in
  each mount string, and the container side of a mount (`/home/dev/.claude/projects`) can contain it. Main's
  `acafe80` ("the session mount test checks only the host side of each mount") fixed it, and that fix is merged here
  (3ff1cae). The file now passes (5 passed). This branch changes nothing in `dev/` or in that test (lesson-13).
- **What that unit run does show.** It ran to its end this time, with no hang or watchdog kill: 1 failed (the test
  above), 1895 passed, and `tests/test_leases.py`, the restart test included, passed under `-n 8`. That is one
  run, with the machine's load not recorded. It is not the 30 loaded runs.
- **No code changed this round.** No earlier finding is still open in code. The fixed sleep was removed in round 3,
  where round 2's non-blocking findings were also answered.
- **The 30 loaded `-n 8` runs: still not run.** This session's harness refused even one watchdogged run
  (`scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py -k test_leases_survive_a_restart`). I did not get
  around that. These runs are still the DoD's one open acceptance line, and only the factory's watched run can record
  them here.
- **Ran serially:** `tests/test_factory_sessions.py` (5 passed) and `tests/test_leases.py` (26 passed). Ruff is
  clean. There is no remote, and local `main` (51ec9b7) is already merged.

### After round 5's unit run (stopped at 51%; no cause found in the branch; no code changed)

- **What the tail showed.** As in rounds 1, 3 and 4: progress dots up to 51%, then nothing. There is no failure line,
  no summary, and no `suite_watch` closing JSON line, so the watcher inside the container was killed from outside
  (`agents.killed`: `docker kill`, run when `fac.suite` is interrupted), not by its own limits. No test is named.
- **Why this does not read as this branch's hang.** Across the five unit runs, the stops came at 73%, before the first
  test (round 3, right after `uv`'s install line, where no test code had run), at 80%, and now at 51%. One run, the
  park's, ran to its end with this same code in 258 s (1895 passed; the only failure was main's test, fixed since).
  A stop before collection cannot come from anything in `ergostat/`. Stops at random points with no watcher line
  fit the suite's container being killed by the factory side (the implementor run interrupted) better than any test
  hanging. That reading is not proven: nothing in the tail shows who sent the kill.
- **Checked again in the code (no change found to make).** Every wait this branch adds has a limit (`close`: the
  engine's lock, at most `lock_wait`; `give_back`: the dispatcher's lock, at most `lock_wait`; the `running` wait,
  5 s, as on main). The lock order is main's: dispatcher, then engine. Both locks are RLocks, so `give_back` inside
  `take` takes the dispatcher's lock again without blocking. The only path from the engine into the dispatcher is
  `run_block` to `once`, which is unchanged from main. `_work`'s early return still runs its `finally`, so the lease
  is ended and `running` is cleared.
- **Decision taken alone (reversible).** No code change: there is no cause to fix, and a change made without one
  would hide what the next run could show. A watched unit run that records why its container was stopped, or runs
  with `-o faulthandler_timeout=300` so a stuck test dumps its stacks, would settle whether a test hangs at all.
  Running main's unit suite in the same slot would show whether main stops the same way.
- **Refused here again:** a serial run of the whole suite with `faulthandler_timeout` (meant to find a hang without
  running in parallel), and a loop over test files.
- **Still open:** the 30 loaded `-n 8` runs of the restart test (the DoD's last acceptance line) and a green unit run.
  The gap is not done.
- **Ran serially:** `tests/test_leases.py` (26 passed); `test_lease_kill`, `test_leased_workspaces`, `test_daemons`
  (39 passed). Ruff is clean. There is no remote, and local `main` is already merged.

### After round 5's second unit run (one `F` at 11%, stopped at 99%; the test not named; no code changed)

- **What the tail showed.** One `F` at about 11%. After it come dots up to 99% and five more, then nothing: no
  failure section, no summary and no `suite_watch` closing line. So the run was again stopped from outside, just
  before its report, and the failing test's name and traceback were never printed.
- **Looked for here, and not found.** In collection order, the first ~23% of the suite runs from `test_architecture`
  through `test_daemons`. Run serially in one process, `test_architecture` through `test_daemon_docs` passed (442
  passed). So did `test_leases`, `test_factory_sessions`, `test_lease_kill`, `test_leased_workspaces` and
  `test_daemons` (70 passed). Under xdist, though, a test at 11% need not come from those files. The failure could
  also be one that only shows under `-n 8` load. This session's harness refused a watchdogged `-n 4` run of those
  files, and the worktree holds no output from the factory's run.
- **Decision taken alone (reversible).** No code change. There is no named test and no cause, and the code can't be
  fixed blind without hiding what the next run would show (lesson-10, lesson-13). The next watched run should keep
  its whole output, or run with `-rf -o faulthandler_timeout=300`, so that a failure is named even if the run is
  stopped before its summary.
- **Still open:** a green unit run, and the 30 loaded `-n 8` runs of the restart test (the DoD's last acceptance
  line). The gap is not done.

### Round 6 (no code changed; the one open line is still the loaded runs)

- **The findings in the brief, each answered (lesson-12).** *The restart test's fixed sleep:* fixed in round 3, and
  still fixed. The test has no `sleep`, judges the record by `seq`, and was seen to fail with the pool count broken.
  *The 30 loaded `-n 8` runs:* still not run (below).
- **The 30 loaded runs: refused again.** This session's harness refused one watchdogged run
  (`scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py`), as it did in rounds 1 to 5. I did not get around
  that. Every implementor round has hit the same refusal, so another implementor round cannot clear this line.
  **Decision taken alone (reversible):** no code changed, because there is no measurement to act on. The factory
  should either record the 30-run counts here from its own watched run, or park the gap with this line as the only
  thing left.
- **The merge of main (213339b, `main-broken`) touches nothing in `ergostat/`,** so the branch's code is the same as
  it was in round 5.
- **Ran serially:** `tests/test_leases.py` (26 passed); `test_lease_kill`, `test_leased_workspaces`, `test_daemons`,
  `test_factory` (80 passed, 2 skipped). Ruff is clean. There is no remote, and local `main` is already merged.

### After round 6's unit run (stopped about 3 results short of the end; no test named; no code changed)

- **What the tail showed.** 27 full progress lines and 18 more results: 1,962 results of the about 1,965 in the park's
  run (1 + 1895 + 69). Then nothing: no failure, no summary and no `suite_watch` closing line. So about three tests
  never reported, and the watcher was stopped from outside.
- **A reading (not proven).** The suite has no per-test timeout (no `pytest-timeout`, no `faulthandler_timeout`), so a
  test that never ends holds its xdist worker until the run is killed. Under `--dist worksteal` the other workers take
  over that worker's queue, except for the test it is running and the one it holds next. That fits "a few results
  short of the end" well: one stuck test is enough. The earlier stops at 51 to 80% (and once before the first dot)
  may be the same thing. The log is a file, so pytest's output can sit in a buffer when the kill comes, and the last
  visible line need not be how far the run really got. Nothing in the tail shows which test, or whether it is one of
  this branch's.
- **Looked for again in the code, and not found.** Every wait this branch adds has a limit (`close`: both locks,
  `lock_wait`; the `running` wait, 5 s). `_work`'s finally takes the dispatcher's lock with no limit, as main's did,
  only to pop `going`. The lock order is still dispatcher, then engine, and no caller of `run_block` (so `once`)
  holds the engine's lock (`_run`, the CLI, the classifier, the step test, the trial). `_kill` kills the run's
  process group, and `stream.pump` ends a killed run's read after its grace. Serially, `tests/test_leases.py` passed
  (26) in 34 s. Its slowest test, `test_a_lease_held_by_a_run_survives_a_model_edit` at 13 s, is not changed here.
- **Refused here:** a serial whole-suite run with `-o faulthandler_timeout=120` (serial, meant to name a stuck test
  by its stacks). I did not get around that.
- **Decision taken alone (reversible).** No code change: there is no cause to fix, and a blind change would hide what
  the next run could show (lesson-10, lesson-13). Adding a per-test timeout to the suite is outside this gap. What
  would settle it is the factory's next unit run with `-o faulthandler_timeout=300` (a stuck test dumps every thread's
  stack, which names it) and unbuffered output (`PYTHONUNBUFFERED=1`), plus main's unit suite run in the same slot.
- **Still open:** a green unit run, and the 30 loaded `-n 8` runs of the restart test (the DoD's last acceptance
  line). The gap is not done.

### After round 6's second unit run (stopped before its first test; no code changed)

- **What the tail showed.** Only the slot line and `uv`'s build and install lines. There were no progress dots, no
  failure, no summary and no `suite_watch` closing line. This looks the same as round 3's stop: the run was ended from
  outside before pytest printed anything. A buffered log could hide some progress, so this does not prove that no test
  ran. Collection is fine here (1964 tests collected in 13 s).
- **Decision taken alone (reversible).** No code change. There is no named test and no cause, and a blind change would
  go against lesson-10 and lesson-13. The seven unit runs so far: six stopped (before the first test twice, and at 51%,
  73%, 80%, 99% and about 3 results short of the end), and one ran to its end with this code. That fits the slot or its
  container being stopped from outside better than a test in this branch hanging, though it is not proven. The factory
  side should find out why its container is stopped, or run main's unit suite in the same slot. Another implementor
  round cannot settle it.
- **Still open:** a green unit run, and the 30 loaded `-n 8` runs of the restart test. The gap is not done.
- **Ran serially:** `tests/test_leases.py` (26 passed), and collection of the whole suite. Ruff is clean.

### Round 7 (no code changed; the one open line is still the loaded runs)

- **The findings in the brief, each answered (lesson-12).** *The restart test's fixed sleep:* fixed in round 3, and
  still fixed. The test has no `sleep`, judges the record by `seq`, and was seen to fail with the pool count broken.
  *The 30 loaded `-n 8` runs:* still not run (below).
- **The merge of main (5231c88) touches nothing in `ergostat/` or `scripts/`,** so the branch's code is the same as it
  was in rounds 5 and 6.
- **The 30 loaded runs: refused again.** This session's harness refused a single watchdogged run
  (`scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py`), as it did in rounds 1 to 6. I did not get around
  that. **Decision taken alone (reversible):** no code changed, because there is no measurement to act on. Seven
  implementor rounds have hit the same refusal. The factory must record the 30-run counts here from its own watched
  run, or park the gap with this line as the one thing left.
- **Ran serially:** `tests/test_leases.py` (26 passed in 34 s). Ruff is clean. There is no remote, and local `main` is
  already merged.
- **Still open:** a green unit run, and the 30 loaded `-n 8` runs of the restart test. The gap is not done.

## Where it stopped

Parked by the factory (review/lease-shutdown-race-3, 2026-11-20 16:35).

Done: the shutdown race is closed. take() checks the stop and registers the run in running under the engine's lock before writing the lease, and gives back uncounted a take that raced the stop. _work does not start a run taken after the stop. run_block kills a process started once this engine is stopping (its own stop, not the process-wide STOPPING). close sets the stop under the lock with a bounded wait and gives back every lease still going before ergostat.stopped. The restart test no longer uses a fixed sleep and is judged by seq order. Seven tests cover the parts, each reported seen to fail with its part disabled. 53 of 120 lines. Left: the DoD's measurement, 30 runs of `scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py` with the CPU loaded, with pass/fail counts recorded. Why stop: every implementor and reviewer session has been refused that run (rounds 1-8), and rounds 3-7 changed no code, so more rounds only repeat the refusal. The factory should run the 30 loaded runs from its own watched slot. If they pass, record the counts and send the branch back to review unchanged. If they fail, the failing run's traceback is the next round's input. Alternatively the owner can amend the DoD.

### Resumed (gap/lease-race-resumed, round 1): code checked after main's merge, loaded runs left to the factory

- **No code changed.** This round's title says the suites and the 30 loaded runs are the factory's to run. So this
  session did not try `suite_watch.py -- pytest -n 8`, which eight earlier rounds were refused.
- **The merge of main (6702105) does touch the lease code.** It adds `takes: {order:}` (`ready.ordered`, which `tick`
  and `once` use to sort what they take). That only orders the list handed to `take`. It does not touch `take`'s
  stop checks, `running`, `_work`, `give_back` or `close`, so the race fix is the same as before. Main's three new
  tests are now in `tests/test_leases.py` as well.
- **Ran serially:** `tests/test_leases.py` (29 passed, including the three acceptance tests), and `test_lease_kill`,
  `test_leased_workspaces`, `test_daemons` and `test_take_order` (43 passed). Ruff is clean. There is no remote, and
  local `main` is already merged.
- **Still open, and both are the factory's:** the DoD's last line (30 runs of
  `scripts/suite_watch.py -- pytest -n 8 tests/test_leases.py` with the CPU loaded, with the pass/fail counts written
  here) and a green unit run.
