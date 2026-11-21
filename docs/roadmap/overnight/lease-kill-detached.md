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
