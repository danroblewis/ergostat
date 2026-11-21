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
