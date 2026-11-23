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

## Where it stopped

Round 2, with no review findings to answer and main unchanged since the last merge (ead497d1 is still main's head),
so there was nothing to merge in and I changed no code. Run again here: ruff is clean, and these tests pass: the four
acceptance tests, test_browser_daily_goal_closes_in_landing and
test_ergostat_check_on_the_factory_model_reports_no_new_finding. I checked the earlier claim that the stray SIGTERM
in the switcher test is not this branch's. Every browser_daily test runs browserday.py as a subprocess only. The one
in-process SIGTERM handler in tests/test_factory.py (the prefix stop test, from main's 34a8a225) puts the old handler
back in its finally. `uv run ergostat check` (as `timeout 300 uv run ergostat check`) was refused again, so done item
6's "no new finding" against main is still unverified.

## Where it stopped

The factory's `build` step failed again (`-n 8 --dist worksteal`). The tail it sent shows one `F` near the start of
the run and stops at 34%, so it does not name the test. Under worksteal, that early position can belong to any
worker's chunk, so I cannot tell from it which test failed. .pytest_cache's lastfailed was empty. Run serially here
(`uv run python scripts/named_tests.py tests/test_factory.py`): 204 passed, 2 skipped (Docker), 0 failed in 922 s. That
includes the five browser_daily tests, the switcher test and the merge test that failed in earlier builds. Ruff is
clean. I changed no code. Nothing here fails, and nothing points at this branch's files. Three builds have now failed
on three different tests or unnamed ones, each passing serially. That fits a load-dependent flake in
tests/test_factory.py under `-n 8` (lesson-10), not a fault in browserday.py. Fixing it is outside this gap
(lesson-13). It cannot be found here until a build's output names the failing test, for example with `-rf` or a
tail that covers the summary. Running test_factory.py under `-n 8` myself is outside the allowed runner (named_tests.py
runs serially, no options). A background run of the same serial command was refused (`run_in_background`); the
foreground one ran.

## Where it stopped

The factory's `build` step failed on test_an_approved_switch_drains_and_switches_through_the_engine: the switcher
was still in `e.running` after the test's 120 s wait (1 failed, 203 passed, 2 skipped, 783 s). I ran it alone on this
branch (`uv run python scripts/named_tests.py
tests/test_factory.py::test_an_approved_switch_drains_and_switches_through_the_engine`): 1 passed in 160 s. I changed
no code, because nothing this branch changes is on that test's path (lesson-13):
- The test starts only the switcher (`run: python3 dev/bin/drain.py`) through the engine. Its loop is not started, so
  browser-daily and its sensor never run there. drain.py reads none of the parts this gap adds (upgrade items, the
  lease-holding gap/research/situation items, run/switch.lock, run/drain.json).
- Each switcher run calls the ergostat CLI several times: `item --kind upgrade` and one listing per state, the
  switch action, and `item --kind` for gap, research and situation in under_way(). Each call loads the whole factory
  model. Alone, the whole test, including its setup, takes 160 s, so the 120 s allowed for one run leaves little
  margin when the machine is busy. That fits a load-dependent wait in main's drain.py and its test (lesson-10), not
  something browserday.py causes. This branch adds three parts to the model (one auxiliary, one goal, one block)
  and no cycle beyond their own loop. That makes each load a little slower, but not enough to be the cause, though I
  did not measure it.
- A fix would cut drain.py's CLI calls or change the test's wait. Both are outside this gap's files, and the test's
  bound must not be raised, so I left them for a gap of their own. Commands refused in this session: timing one CLI
  call (`time (uv run ergostat -C . item --kind upgrade >/dev/null 2>&1); nproc; uptime`) and an awk listing of
  engine.py's run_block. Neither was worked around. I did not run the test on main, because a worktree of main was
  refused in an earlier round.

## Where it stopped

Round 3: merged main (5411f137). The one conflict was in tests/test_factory.py. Main replaced dev/bin/prefixes.py
with halves.py and removed the prefix tests, and this branch's browser_daily tests came after them. I kept main's
removal and the branch's tests. Main had also dropped `import signal`, which test_browser_daily_holds_the_queue_lock
still uses, so I put it back. browserday.py needed no change, since it uses nothing from prefixes.py. After the
merge, ruff is clean and these pass: the four acceptance tests, test_browser_daily_goal_closes_in_landing and
test_ergostat_check_on_the_factory_model_reports_no_new_finding. The unit suite and the four browser files were not
run here (the factory's and the queue's steps). Done item 6's "no new finding" against main is still unverified by a
full `ergostat check`. Two shell commands were refused this round: a git status piped through grep, used to list
the conflicts, and a short python script to cut the conflict block. I did both with the file tools instead.

## Where it stopped

The factory's `build` step failed on test_an_approved_switch_drains_and_switches_through_the_engine again: the
switcher was still running after the test's 120 s wait (1 failed, 194 passed, 2 skipped, 913 s). The merge of main
(5411f137) was already committed (d112704c), so there was nothing left to resolve. This time I measured whether this
branch's model parts are the cause, since a model load is the one thing this branch adds to that test's path. I ran
the test alone twice: once on the branch as it is, and once with the branch's three parts (the auxiliary and goal
browser-main-green and the block browser-daily) taken out of dev/model/landing.yaml with the file editor, so the file
matched main's. I then put them back, and `git status` was clean afterwards.
- Branch's model: 1 passed in 143.59 s. Main's landing.yaml: 1 passed in 142.82 s. The difference is 0.8 s across
  the whole test, so the branch's additions do not measurably slow the switcher's CLI loads.
- The test starts only the switcher (`python3 dev/bin/drain.py`). Each of its steps makes about 15 ergostat calls,
  and each call loads the whole model: fac.items("upgrade") lists once plus once per state, action_state makes one
  call, under_way() lists three kinds with the same per-state calls, and each fac.say makes one more. Each step has to
  finish inside the test's 120 s, and the test alone takes about 143 s in all. So the margin is thin when 8 workers
  share the machine. That is a load-dependent wait in main's drain.py and its test (lesson-10). It passes alone, the
  same way, with or without this branch.
- I changed no code. The fix is to cut drain.py's CLI calls, for example one listing for under_way() instead of one
  per kind and state, or to change how the test waits. Both are outside this gap's files (lesson-13), and the test's
  bound must not be raised. I leave it for a gap of its own: the switcher test is slow under `-n 8` on main's
  drain.py.
- Refused this round, and not worked around: `git diff main -- dev/model/landing.yaml; nproc; cat /proc/loadavg`, a
  `uv run python -c` timing of `model.load`, `cp` of landing.yaml to /tmp followed by `git show main:...` into it, and
  `git checkout HEAD -- dev/model/landing.yaml`. In their place I ran the plain `git diff`, edited the file with the
  editor, and timed the test with named_tests.py.

## Where it stopped

The factory's `build` step failed again on test_an_approved_switch_drains_and_switches_through_the_engine (the
switcher still in `e.running` after the test's 120 s wait; 1 failed, 194 passed, 2 skipped, 663 s). The merge of main
(5411f137) was already committed (6f406d72, d112704c): `git status` was clean, so there was nothing to resolve. I
changed no code. `git diff main --stat` shows the branch touches only dev/README.md, dev/bin/browserday.py,
dev/model/landing.yaml, this record and tests/test_factory.py. It does not touch drain.py, the engine or the test.
The previous round measured this test alone at 143.6 s with the branch's model and 142.8 s with main's. The code to
fix (drain.py's per-kind, per-state CLI calls, each one loading the whole model) is main's and outside this gap
(lesson-13), and the test's bound must not be raised. This is the same failure as the last four builds, so I did not
run the test again. It needs a gap of its own: the switcher test is too slow under `-n 8` on main's drain.py. Until
that gap lands, this one waits on it. Refused this round: a heredoc append to this file followed by `git commit -qam`
in one shell command. I wrote this section with the file editor instead.

## Where it stopped

Round 4, with no review findings to answer. Main (7a905955) is already merged into the branch (8761273b), and `git
diff main --stat` shows only this gap's five files, so there was nothing to merge and I changed no code. After that
merge, ruff is clean and these pass, run on this branch: the four acceptance tests,
test_browser_daily_goal_closes_in_landing and test_ergostat_check_on_the_factory_model_reports_no_new_finding (two runs
of three tests: 3 passed in 189 s, 3 passed in 375 s). Main's d3f08d49 isolates the rerun-timing test. Nothing on main
since 5411f137 addresses the switcher test's 120 s wait (test_an_approved_switch_drains_and_switches_through_the_engine),
so a build under `-n 8` may still fail on it, as reported above. That failure is outside this gap. I did not run the
unit suite or the four browser files (the factory's and the queue's steps). `uv run ergostat check` was refused again,
so done item 6's "no new finding" against main is still unverified by a full check.

## Where it stopped

The factory's `build` step failed again (tests/test_factory.py, `-n 8`). The tail stops at "bringing up nodes...", so
it names no test, and I cannot say which one failed. I looked through this branch's own tests for a check that
depends on load and found one in test_browser_daily_holds_the_queue_lock. After the SIGTERM it checked, with a single
`os.kill(pid, 0)`, that the stand-in browser suite's shell was gone. fac.suite waits only for its direct child
(`sh -c`, shell=True). When the shell is a grandchild, it is killed with the group, but init has to reap it, and until
then `os.kill` succeeds on the zombie. So the check could fail under load. It now polls for up to 10 s
(`daily_gone`): the process counts as gone when it no longer exists or /proc shows it as a zombie. When /proc cannot be
read (macOS), the process counts as still alive (lesson-3). This is a test-only change. browserday.py and fac.py are
unchanged, and no code bound was raised. I am guessing that this was the build's failure, because the tail does not
show it. If the next build fails, its named test is the place to start, and the switcher test (above) is still the
likelier cause. I could not reproduce the zombie window: a shell command that checks PID 1 and whether `sh -c` execs
its last command (`cat /proc/1/comm; ls -l /bin/sh; sh -c 'sh -c "echo \$\$ \$PPID"; echo $$'`) was refused. Run
here: ruff is clean, and test_browser_daily_holds_the_queue_lock, test_browser_daily_green_records_main and
test_browser_daily_failure_names_tests_and_suspects pass (3 passed, 201 s).
