# queue-runs-what-its-container-skips: the tests the queue's container cannot run still gate a merge

depends-on: []

Since the merge queue moved into Docker, its unit suite skips 52 tests that passed on the Mac: `tests/test_repair2.py` (32) and `tests/test_sandbox_attacks.py` (20), because bwrap cannot make its namespaces in the container, and `tests/test_notify.py`'s kqueue test. They are the tests of the AI repair sandbox. Nothing checks them before a merge now, and a skip reads as green.

## Definition of done
1. A `[suites] host` command in `dev/factory.toml` names these tests. The queue runs it on the Mac, outside the container, on the batch's merge, under the queue's lock, as a required step: a failure fails the batch and bisects like any suite. An empty value turns the step off.
2. The step's result is written beside the others in `run/queue/` and counted in the run's outcome.
3. A test that needs the sandbox and is skipped in **both** places fails the queue run, so the gate cannot go silently empty. Skips with a stated external need (a server URL, money, playwright in the unit suite) are unaffected.
4. SPEC or the docs page on the merge queue says which tests run where.

## Files to touch
`dev/bin/queue.py`, `dev/bin/fac.py`, `dev/factory.toml`, tests, docs.

## Risks
- lesson-3: a host step that cannot run is a failure of the run, never a pass.
- It must not need a live instance or Docker to test: use a fake suite command in unit tests.

## Acceptance tests
- a failing host step fails the batch and bisects
- an empty `[suites] host` skips the step
- a host step that cannot start is not read as passing

## Size budget
60 net lines of code outside `tests/` and `docs/`.
