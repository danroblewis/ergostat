# triage-off-the-lock: Flake triage never holds the queue's lock

depends-on: []

Measured 2026-11-21: triage held or was next in line for the queue's lock for 20.8 of 480 minutes.

## Definition of done
Triage reruns tests in its own worktree under a suite slot only, so neither its run nor a load wait can block the queue.

## Files to touch
`dev/bin/triage.py`, `tests/test_factory.py`, `dev/README.md`.

## Risks
- lesson-1: triage judges the exact commit that failed, whatever main has become.

## Acceptance tests
- `tests/test_factory.py::test_triage_runs_while_the_queue_holds_its_lock`
- `tests/test_factory.py::test_triage_waiting_on_load_does_not_block_the_queue`

## Size budget
15 net lines of code outside `tests/` and `docs/`.
