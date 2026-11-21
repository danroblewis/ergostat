# lease-kill-detached: A lease kill reaches a detached process whose parent exited

depends-on: []

Audit 2026-11-21, reproduced: `ergostat/leases/kill.py` looks only at the live process tree. A run that starts a background process in its own session, whose intermediate parent exits, survives the kill with parent pid 1. SPEC says the kill reaches "every process it started (in whatever group or session)". `reap.Watch` exists for this but only `library/trial.py` uses it.

## Definition of done
Each run has a `Watch`, and a lease kill stops everything it saw, including detached children, without touching a reused pid.

## Files to touch
`ergostat/leases/kill.py`, `ergostat/spec/engine.py`, `tests/test_resilience.py`.

## Risks
- lesson-5: a reused pid is never killed.

## Acceptance tests
- `tests/test_resilience.py::test_a_lease_kill_reaches_a_detached_child`
- `tests/test_resilience.py::test_a_lease_kill_leaves_a_reused_pid_alone`

## Size budget
40 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built, within budget (+51 −17 = 34 net lines in `ergostat/`, docstrings counted).

- `spec/engine.py`: each machine run gets a `reap.Watch` on its pid when it is spawned (`proc.watch`), closed when it
  ends.
- `leases/kill.py`: the kill looks once more, then passes the watch's `still` to `reap.stop`, so the detached processes
  it saw are signalled along with the live tree.
- **Outside the files to touch: `ergostat/library/reap.py`** (+40 −15). A set of pids is not enough for lesson-5: a pid
  the watch saw could belong to another process by kill time, or by the SIGKILL round up to the grace later. I made
  the most reversible choice and put the fix where the `Watch` lives, not in a copy in `kill.py`. `tree()` now also
  reads each process's start time (`ps ... lstart=`, from the same look), the `Watch` keeps each pid with the start
  time it was first seen with, and `still()` names only the pids that still match. `stop(also=...)` also accepts a
  function, which it calls again at each signal round. In that mode it looks under `pid` only while `pid` is still
  the process it saw. The set form used by `library/trial.py` works as before (`tests/test_trial_stops.py` passes).
- Limits, also stated in SPEC §9.5: the watch looks every 0.5 s, so a child started and abandoned within one look is not
  seen. `lstart` is accurate to one second, so a pid freed and taken again within the same second as the first start
  is not told apart. Between `still()` and the signal there is a window of milliseconds.
- Both acceptance tests were seen to fail with the fix broken: with `also={proc.pid}` (no watch), both fail; with
  `still()` ignoring the start time, the reused-pid test fails ("a pid used again is left alone").
- Run, one file at a time: `test_resilience.py` (26 passed), `test_lease_kill.py` (10), `test_leases.py` (29),
  `test_trial_stops.py` (2), `test_streamed_output.py` (10). Ruff is clean. Not run: the full unit suite and the
  browser files (the factory runs them under the watchdog). This clone has no `origin/main` ref; local `main` has
  nothing this branch lacks (`git rev-list --count HEAD..main` is 0), so nothing was merged.

After the fast suites, round 1: `unit` failed on `test_notify.py::test_a_run_costs_one_thread` (61 threads for 30
runs, against 34) and `test_leases.py::test_the_watchdog_renews_from_what_the_holder_does_elsewhere` (it passes alone).
Both came from this branch: each `Watch` had a thread of its own and ran its own `ps` every 0.5 s, so every run cost
a second thread, and 30 runs forked about 60 `ps` a second, which slowed the lease watchdog under load. Fixed in
`library/reap.py`: every open `Watch` shares one looker thread (started with the first, ended when none is open) and
one `ps` a look. The engine's `close(look=False)` drops the last `ps` at each run's end (`trial.py` keeps its last
look). Both tests now pass, along with `test_leases.py`, `test_resilience.py`, `test_trial_stops.py` and
`test_run_costs.py` (one file at a time); ruff is clean.

**Size overrun, the reason:** `ergostat/` now counts +89 −28 = 61 net lines against 40 (docstrings and comments
counted). The 21 over are the shared looker. A run with its own thread breaks the house rule that a run costs one
thread (test_notify's bound), and this machine has panicked from thread exhaustion, so a thread per run is not a
safe way to stay within budget. The rest is as counted in round 1.

Round 2, answering review/lease-kill-detached-1 (every finding):

- **Blocking, lesson-3 (`ps` fails, nothing signalled):** fixed. `kill.py` now passes `stop` a function that adds the
  run's own pid while `proc.poll()` is None (an unwaited child of this engine, so never a reused pid) to the watch's
  `still()`. `stop` looks under it and signals its group, taken from the kernel (`os.getpgid`) when `ps` gave
  nothing. New test `test_a_lease_kill_still_stops_the_run_when_ps_fails` (with `reap.tree` returning `{}`, the run
  and the child in its group are stopped). With the run's pid left out, it fails.
- **SIGKILL round used only `also()`:** fixed in `reap.stop`. In callable mode each round keeps the pids it signalled
  with their start times (from that round's `ps`), and the next round adds those still the same process, so a child
  found by the TERM scan that ignores TERM gets SIGKILL even after its run has died. The reused-pid rule still holds.
  No test of its own: the window (a child started between `look()` and the TERM scan) can't be hit reliably
  without hooks into `stop`. This is stated here rather than claimed as tested.
- **Watch opened before the try/finally (`engine.py`):** fixed. The `Watch` is now made immediately before the `try`
  whose `finally` closes it, after `old._kill`, the lock block and `SAMPLER.track`. `reap._looker` adds a watch to
  the open set only after the looker thread has started, so a failed thread start leaves nothing open. A kill that
  arrives before the watch exists still stops the run and its tree (the run's own pid, above).
- **Size, "no reason written":** the reason is restated below so the gate can find it.

**Size overrun, the reason (round 2):** `ergostat/` counts +102 −32 = 70 net lines against 40 (+75%, docstrings and
comments counted): `reap.py` +58, `kill.py` +9, `engine.py` +3. Over budget: the shared looker (about 21, so that a
run costs one thread; the reason is above), the start-time check (lesson-5, without which a pid used again is
signalled), and this round's fail-closed fixes (about 9: the run's own pid and its group when `ps` fails, and the
SIGKILL round's re-check). Each is needed for a finding or a house rule. Without them the code would be smaller and
not safe.

Limits, unchanged: one look every 0.5 s; `lstart` is good to one second; between `still()`/`poll()` and the signal
there is a window of microseconds to milliseconds (main had the same window for the run's own pid).

Run, one file at a time: `test_resilience.py` (29 passed), `test_lease_kill.py` (10), `test_leases.py` (29),
`test_trial_stops.py` (2), `test_notify.py` (4, 1 skipped: kqueue, macOS only; `test_a_run_costs_one_thread`
passes), `test_run_costs.py` (14), `test_streamed_output.py` (10). Ruff is clean. Not run: the full unit suite and the
browser files (the factory runs them). Local `main` has nothing this branch lacks (`git rev-list --count HEAD..main`
is 0), and there is no `origin/main` in this clone, so nothing was merged.

Round 3, answering review/lease-kill-detached-2 (every finding):

- **Merge of main (0441187f, with rs-detach):** `tests/test_resilience.py` conflicted; both sides kept (this branch's
  lease-kill tests, then main's section 6). The engine merged cleanly: the run is now main's wrapper
  (`runrecord.command`) in a session of its own, and its watch is on the wrapper's pid, so the command and what it
  starts are under it.
- **Blocking, lesson-12/lesson-6 (the Watch made before the try):** fixed for real this time. Round 2's subject
  claimed it and the code did not do it; that claim was wrong. `proc.watch` is now set to None, then the `Watch` is
  built *inside* the `try` whose `finally` reads, waits on and takes the run off the lists. A `RuntimeError` from it
  (no thread to spare) leaves `proc.watch` None, and the run is followed as any run. `kill.py` already handles a run
  with no watch: it still signals the run's own pid and its group. The `finally` closes the watch only if it exists.
  New test `test_a_run_whose_watch_cannot_start_still_ends_as_a_run` (`reap.Watch` raising: the run is read, its
  `agent.failed` recorded, `procs`/`live` emptied). With the `except` broken it fails.
- **Lesson-8, the lstart limit not in SPEC or the kill.py docstring:** both now say start times are read to the
  second, so a pid freed and taken again within the same second as its first start is not told apart.
- **`Watch.look`'s `setdefault` (a pid the run had, reused by another child of the same run):** fixed. A pid under
  the run at this look gets the start time it has now (it is the run's, whatever held the pid before). The run's own
  pid keeps its first stamp. New test `test_a_watch_knows_a_pid_its_run_took_again`; with `setdefault` back, it fails.
- **Size:** answered below.

**Size overrun, the reason (round 3):** `ergostat/` counts +108 −33 = 75 net lines against 40 (+88%, docstrings and
comments counted): `reap.py` +58, `kill.py` +9, `engine.py` +8. Since round 2: +5 in `engine.py` (the watch built
inside the try, with its fallback, and the guarded close), and the docstring's lstart limit. The reasons for the rest
are those of round 2: the shared looker (so a run costs one thread), the start-time check (lesson-5), and the
fail-closed paths (lesson-3). Each answers a finding or a house rule.

Run, one file at a time, after the merge: `test_resilience.py` (40 passed), `test_lease_kill.py` +
`test_trial_stops.py` (12), `test_leases.py` (29), `test_notify.py` (4, 1 skipped: kqueue, macOS only),
`test_run_costs.py` (14), `test_streamed_output.py` (10). Ruff is clean. Not run: the full unit suite and the browser
files (the factory runs them).
