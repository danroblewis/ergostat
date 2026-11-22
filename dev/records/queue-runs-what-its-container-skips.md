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

Round 2:
- The factory's merge of main (c1d10970) conflicted in dev/bin/queue.py (the docstring: main's stall sentence and the
  branch's host sentence, both kept) and dev/bin/triage.py (main's `fac.Stalled` handling now wraps the branch's
  `rerun(..., failed_suite)` call). The host step goes through `fac.suite` like the others, so main's stall limits
  apply to it too.
- Round-1 finding on `queue.EXTERNAL` (substrings, case-insensitive, so "needs curl" or "not under Docker" were
  exempt): it is now an allowlist of the exact external reasons the tests use, case-sensitive and anchored; a new
  external skip reason must be added there or it counts as ran-nowhere (fail closed). Test:
  `test_only_the_stated_external_needs_in_use_are_exempt`, seen to fail with the old pattern.
- Round-1 finding that a Mac-wide host fault (sandbox-exec gone) is red on every prefix, so the bisect blames the
  batch's first gap: left as is. It is how every suite bisects, the definition asks the host step to bisect "like any
  suite", and triage then sends the gap back with the named failure, so nothing wrong lands. Telling a Mac fault from a
  branch's would need a run of the base on its own, a change to the bisect for every suite: its own gap.

Round 3:
- Round-2 finding (blocking): round 2's note that "main's stall limits apply to it too" was false. The host step ran
  with box="", and fac.suite applied limits(), the stall and wall checks and faulthandler_timeout only when box was
  set. `fac.suite` now takes box="host": the limits apply, but it is never put in a container. The queue's host step
  and triage's rerun of a host failure both pass it. Tests: `test_a_host_step_that_stops_writing_is_stopped_as_a_stall`
  (Stalled, the run undone, no gap blamed, the process group gone) and
  `test_a_triage_rerun_of_the_host_step_is_limited_too`. Both were seen to time out with the old box="". Removing the
  `box != "host"` guard was seen to fail `test_a_failing_host_step_fails_the_batch_and_bisects` (its triage rerun
  needed docker).
- Round-2 finding (quarantine covers only unit and browser): documented in dev/README.md's quarantine paragraph, not
  extended. Deselecting a quarantined sandbox test from the host step would run it "beside" in the container, where
  it only skips, so it would never be run anywhere (lesson-3). The way it works now fails closed.
- Round-2 "not run by this reviewer": this round ran tests/test_queue_host.py (9 passed) and tests/test_queue.py
  (13 passed). The clone still has only a local `main` (`git branch -a`: this branch and main), already an ancestor
  of HEAD, so there was nothing to merge.
