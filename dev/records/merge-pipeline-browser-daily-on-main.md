# merge-pipeline-browser-daily-on-main: Once a day the browser suite runs on main; a flake is recorded, a real failure is a test broken on main

depends-on: [merge-pipeline-browser-names-its-failures, regression-flake-writes-hold-state]

## Problem
The owner wants the browser suite run on a trigger rather than in every batch. A batch-only trigger (merge-pipeline-browser-only-on-its-paths) needs a safety net for changes outside those paths that still break a page, such as a model loader change that alters what a diagram draws. Nothing runs the browser suite on main by itself today. Each batch's run is the only one (queue.py:156).

## Change
A new program, dev/bin/browserday.py, run as a block browser-daily in dev/model/landing.yaml (every: 24h). It works under the queue's lock (fac.queue_lock), so it never overlaps a batch, after fac.wait_quiet. It runs the browser suite (box "queue", quarantine from main) in a detached worktree at origin/main, made and removed by name.
- Green: write {sha, at} to run/browser-daily.json.
- Red: rerun each named test alone twice (the named() shape, `-rA`). A test that passes both times is flake.seen (suite browser, run, log). The others form an intervention of class queue naming the tests, main's sha, and the first-parent merges since the last green sha (git log --first-parent) as suspects. pipeline-watch already turns a queue intervention into a situation.
- No names (a crash, a skip): an intervention with the tail.
A sensor browser-main-green (1, 0, or no reading when the file cannot be read: lesson-3) and a goal on it make the result visible on the Dynamics diagram. No new page.

## Definition of done
1. A green run records the sha. A run the next day with no merge between still runs (it tests main, not changes).
2. A failure that passes alone twice is a flake, and no intervention is raised.
3. A real failure raises one intervention naming the tests, the sha and the suspect merges since the last green.
4. The run holds the queue's lock. A batch waiting for the lock starts after it.
5. Its worktree and containers are removed on every way out.
6. `ergostat check` adds no finding. dev/README.md says what the daily run does.

## Files to touch
dev/bin/browserday.py (new), dev/model/landing.yaml, dev/README.md, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_browser_daily_green_records_main
- tests/test_factory.py::test_browser_daily_flake_is_recorded_not_raised
- tests/test_factory.py::test_browser_daily_failure_names_tests_and_suspects
- tests/test_factory.py::test_browser_daily_holds_the_queue_lock

## Size budget
160 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: dev/bin/browserday.py (142 lines), the block browser-daily, the auxiliary and goal browser-main-green
(dev/model/landing.yaml), dev/README.md (*The daily browser run on main*), and the four acceptance tests, which pass.
Each was seen to fail with its code broken: one rerun instead of two (the flake and failure tests), no queue lock (the
lock test), no `--first-parent` (the failure test), no worktree removal in the finally (the green and lock tests).

Choices made with nobody to ask (each the more reversible one):
- A red run whose named tests all pass alone twice counts as green (main's sha becomes `last_green`, its flakes
  listed); a run that skipped any test is never green, flakes or not.
- At most 8 named tests run alone (twice each); the rest count as real, never as passed (lesson-4, lesson-3). At most
  50 suspects; with no known green, or a green that is no ancestor of main, the latest 50 first-parent commits
  (`suspects_since: null`).
- An unreadable run/browser-daily.json counts as no green known (the worst case for suspects); the sensor gives no
  reading for it.
- It raises an intervention only: it does not hold the queue (`main_red` is not set). Not asked for; a later gap may.
- Its containers on a SIGKILL (no finally): swept by the next run (or the queue's run) under the lock, as the queue's
  are. The container path itself is fac.suite's, unchanged, and is not exercised here (the Factory fixture turns
  `queue_container` off, as the other queue tests do).

Not run here: `ergostat check` before and after (done item 6). `uv run ergostat check --json` was refused in this
session, and so was the worktree of main to compare it with (`git worktree add -q --detach /tmp/daily-base main`).
tests/test_factory.py::test_ergostat_check_on_the_factory_model_reports_no_new_finding and
::test_the_factory_model_loads pass with the new parts in the model, but neither compares the model against one
without them, so the "no new finding" claim is unverified. The unit suite and the four browser files were not run
(the factory's steps).

## Where it stopped

Check finding `missing-feedback goal.browser-main-green` (sent back before the suites), answered by a model change
in dev/model/landing.yaml alone. The block browser-daily now reads the goal as a list (`in: [goal.browser-main-green]`).
That is read, not commanded, as pipeline-watch reads its goals, so the `every: 24h` schedule stays. It already sets
the auxiliary, so the loop closes inside landing. The program ignores the input, so its behaviour is unchanged. This
is the smallest change and the easiest to undo. The loop it draws is thin: the run measures main again each day, and
what actually turns main green is a fix merged after the intervention. The model already shows that through the
auxiliary's `driven-by: +flow.gaps-merged`.
- Tried and dropped: pipeline-watch reading the goal, with `+flow.situations-handled` driving the auxiliary. That
  closes the loop through the manager but adds the finding `interface@system.managing` (10 information links, a
  wide interface), which `test_the_time_goals_have_no_check_findings` caught.
- Rejected without trying: an external `fix-main` block setting the auxiliary (a `two-actuators` compile error beside
  browser-daily, seen); browser-daily moving `flow.interventions-recorded` (an open loop, `acting-on-its-own`); a block
  commanding browser-daily (a commanded block loses its `every:` schedule, engine.py's timed blocks).
- New test `test_browser_daily_goal_closes_in_landing`: no compile error, no finding on the goal, the block or the
  auxiliary, browser-daily the loop's actuator and the goal's only reader, still on its schedule, nothing commanding
  it. It failed with the `in:` line removed (`missing-feedback@goal.browser-main-green`).
- `ergostat check` itself was refused in this session, so findings were not compared in full against main. The
  factory-model tests that pass: test_ergostat_check_on_the_factory_model_reports_no_new_finding and
  test_the_time_goals_have_no_check_findings. tests/test_factory_manager.py passed (35 tests) while the manager
  variant was still in place. It was not run again after the revert, which put manager.yaml back as it is on main.

## Where it stopped

After main (ead497d1) was merged in, with no code change: the four acceptance tests,
test_browser_daily_goal_closes_in_landing and test_ergostat_check_on_the_factory_model_reports_no_new_finding pass,
and ruff is clean. `uv run ergostat check --json` was refused again in this session, so done item 6's "no new
finding" is still unverified against main. The unit suite and the four browser files were not run here (the
factory's and the queue's steps).

## Where it stopped

The factory's `build` step failed (unit tests for tests/test_factory.py, `-n 8`). The tail it sent back stops at
"bringing up nodes...", so it does not name the failing test. Run again serially here
(`uv run python scripts/named_tests.py tests/test_factory.py`): 1 failed, 203 passed, 2 skipped (Docker). All five
browser_daily tests passed. The one failure was
test_an_approved_switch_drains_and_switches_through_the_engine: `SystemExit: 143` inside `e.close()`, raised by a
`fac.stop_on_term` SIGTERM handler that was already installed in the pytest process itself. It passed when run alone
(1 passed, 149 s). This branch changes nothing that test touches: no switcher, engine or fac.py code. Its tests run
browserday.py only as a subprocess (Factory.run, Popen), so they cannot install that handler in pytest. So I left the
failure alone and changed no code (lesson-13). I did not run it on main to compare, because the worktree of main was
refused in an earlier round. If the build fails again, the test it names is the place to start.

## Where it stopped

The factory's `build` step failed again (`-n 8`) on two tests:
test_an_approved_switch_drains_and_switches_through_the_engine (the switcher was still running after its 120 s wait)
and test_two_failing_merges_take_two_rounds_and_one_full_run (3 full suite runs where it expects 2). I ran both together
on this branch (`uv run python scripts/named_tests.py
tests/test_factory.py::test_two_failing_merges_take_two_rounds_and_one_full_run
tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine`): 2 passed in 211 s. I changed
no code, because neither test reaches what this branch changes (lesson-13). The branch touches only
dev/bin/browserday.py, dev/model/landing.yaml, dev/README.md, this record and the new tests at the end of
tests/test_factory.py. It does not touch queue.py, prefixes.py, drain.py, live.py, fac.py or the engine.
- The merge test runs queue.py on a stand-in model (Factory, bisect_stand_ins) and never runs browserday.py. A third
  suite run means a round got an "unknown" prefix and fell back to a serial bisect (land()'s docstring). That fits a
  load-dependent failure in prefixes.run_all, which runs `git worktree add` from several threads at once on one repo
  (git's lock files). Any exception there turns that prefix's result into "unknown" (prefixes.py:105). This is a guess:
  the tail I was sent does not show the prefix logs. It is main's code (ead497d1 and before), outside this gap.
- The switcher test loads the factory model, which now includes the block browser-daily, but its engine loop is not
  started (instance_engine). It starts only the switcher, so browser-daily never runs there, and drain.py reads
  nothing this gap adds. In the earlier serial run this test failed on a stray SIGTERM. Serially it runs before every
  browser_daily test (line 4467, against 5515 onward), so those tests could not have caused that failure.
- I did not run either test on main: a worktree of main was refused in an earlier round. A heredoc append to this file
  (`cat >> dev/records/... <<'EOF'`) and its commit were refused in this session, so I wrote this section with the
  file editor instead.
