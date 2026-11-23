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
