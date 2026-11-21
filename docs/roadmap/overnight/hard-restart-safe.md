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
