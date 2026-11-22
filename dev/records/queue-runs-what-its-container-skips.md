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

## Where it stopped

Built; nothing left that I know of. Judgement calls, each taken as the most reversible option:
- The docs page is dev/README.md ("Which tests run where", under "The suites in the queue"). SPEC is unchanged.
- `[suites] host` that is absent counts as empty (the step is off), like `""`. Otherwise every test fixture config
  without the key would need changing. To make an absent key an error instead, change one line in `queue.host_on`.
- The host step runs after unit and browser and before demo, on its own (no container's load beside it), with
  `-n 4`. A host failure is never excused as a flake in the queue: its named rerun goes to the container, where those
  tests skip, so it reads "cannot tell" and the bisect runs in full.
- `dev/bin/triage.py` was not listed under "Files to touch" but is changed by 3 net lines. Without the change, flake
  triage reran a host failure's tests in the container, where they skip with rc 0, so a real sandbox failure would have
  been called a flake (lesson-3). `dev/bin/fac.py` needed no change: `fac.suite` with no `box` already runs on the Mac.
- "Skipped in both places" compares the host log's `-rs` lines with the same run's unit log by `path:line`. So
  `[suites] unit` now has `-rs`. When the unit log is missing (an excused run's leftover suites), or counts skips
  without naming them, every host skip counts as one that ran nowhere (fail closed). A stated external need is an
  allowlist of reason words (`queue.EXTERNAL`: URL, money, Chromium, playwright, Docker, free ports).
- Exit 126 or 127 from the host step raises agents.NotStarted, the same path a container that did not start takes:
  the run fails and is undone, with no gap blamed.
- The clone has no `origin/main` ref (only local `main`, already an ancestor of the branch) and no network, so there
  was nothing to merge in.
