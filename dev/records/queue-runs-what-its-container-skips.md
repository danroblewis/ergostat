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

Round 4:
- Queue finding `tests/test_factory.py::test_the_shipped_build_setting_runs_the_small_set`: this branch's. Round 1
  added `-rs` to `[suites] unit`, and the test holds `build` to end with unit's pytest arguments. `build` now has
  `-rs` too. That only names skips in its output. Seen to fail before the change and pass after.
- Queue finding `tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`:
  it passes here, alone and with the rest of tests/test_agents.py (16 passed). I think it is main's, not this branch's.
  The test (8212a01f, on main) asserts the docker `-e` is exactly `PYTEST_ADDOPTS=-o faulthandler_timeout=300`.
  fac.suite (main's code, line 480) appends to the caller's PYTEST_ADDOPTS. Inside the queue's own boxed unit run,
  that variable is already `-o faulthandler_timeout=300`, so the stand-in gets the option twice and the exact match
  fails. Outside the queue it is unset and the test passes. I did not reproduce it: running it with PYTEST_ADDOPTS set
  (`PYTEST_ADDOPTS="-o faulthandler_timeout=300" uv run python scripts/named_tests.py tests/test_agents.py::...`) was
  refused in this session. Not fixed here (lesson-13). It belongs to its own gap: fac.suite should drop an inherited
  faulthandler_timeout, or the test should clear PYTEST_ADDOPTS in the factory's env.
- Round-3 finding (126/127 is the outer shell's exit): dev/README.md and queue.py's docstring now say so. They also
  say that a pytest missing behind suite_watch.py/uv exits 1 and counts as a real red host failure (fails closed).
- Round-3 finding (triage's host rerun with 126/127 was read as a red rerun that blames the branch): triage.rerun now
  raises agents.NotStarted for it, as the queue's host step does, so no gap is sent back. Test:
  `test_a_triage_rerun_of_the_host_step_that_cannot_start_blames_no_gap`. With the guard replaced by `if False:`, it
  was seen to fail (the gap was sent back).
- Round-1 finding left open until now (the missing-unit-log branch of nowhere() had no test): added
  `test_a_missing_unit_log_counts_every_host_skip_as_nowhere`.
- Round-3 "not run by this reviewer": this round ran tests/test_queue_host.py (11 passed), tests/test_queue.py (13
  passed), tests/test_agents.py (16 passed) and the build-setting test (passed). Ruff is clean on ergostat, tests and
  scripts, and on the three dev/bin files changed. Ruff on all of dev/bin reports 3 errors: two in plan.py and
  review.py, which this branch does not touch, and one that was mine in queue.py, now fixed. The clone still has only
  a local `main`, already an ancestor of HEAD, so there was nothing to merge.

Round 5:
- Queue finding (batch of 6, then alone)
  `tests/test_agents.py::test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network`: not fixed
  here (lesson-13), as the round-4 review agreed. The line it trips on, fac.suite's
  `env["PYTEST_ADDOPTS"] = f"{env.get('PYTEST_ADDOPTS', '')} -o faulthandler_timeout=..."`, is unchanged from main
  (`git diff main -- dev/bin/fac.py` touches only the docstring and the `box != "host"` guard, and "host" is never
  passed in that test). Inside a queue container PYTEST_ADDOPTS is already set, so the exact `-e` match fails for any
  branch. It passes here outside the queue (1 passed). It needs its own gap on main.
- Round-4 review (wording): the "Which tests run where" and quarantine paragraphs of dev/README.md and the fac.suite
  docstring's last line are reflowed to the wrap width (118 in that section, 120 in fac.py). No code changed.
- Round-4 "not run by this reviewer": this round ran tests/test_queue_host.py (11 passed) and the test_agents test
  above (1 passed); ruff is clean on ergostat, tests, scripts and the three dev/bin files changed.

Round 6:
- Round-5 finding (blocking, `-rs` drops the FAILED lines): confirmed. scripts/named_tests.py runs `pytest -q -rs`,
  and a failing test run through it printed `1 failed` and no `FAILED path::test` summary line. `[suites] unit`,
  `build` and `host` now carry `-rfEs`, so fac.failed_tests still names their failures. Test:
  `test_the_shipped_suites_name_their_failures_and_their_skips` (each of the three keeps f, E and s in every -r).
  With `build` put back to `-rs` it was seen to fail (`('build', ['s'])`), and it passes with `-rfEs`.
- Not changed here (lesson-13): `[suites] browser` and `rerun` carry `-rs` from main (not this branch), so the same
  loss of FAILED lines applies to browser failures on main. tests/test_agents.py:36 holds them to the substring
  ` -rs `, so the fix there also needs that test changed. It belongs to its own gap on main.
- Round-5 "not run by this reviewer": the run that was asked for is the one above. This round ran
  tests/test_queue_host.py (12 passed, 242 s), the build-setting test and test_implementor_environment_has_a_browser
  (2 passed); ruff is clean on ergostat, tests, scripts and the three dev/bin files changed.
- Round-5 test_agents finding (main's PYTEST_ADDOPTS): unchanged, as in round 5. Round-5 README wording: answered in
  round 5.
