# regression-flake-fixed-after-green: A seen flake is fixed after N green queue runs that each say it passed

depends-on: [regression-flake-writes-hold-state, merge-pipeline-browser-names-its-failures]

Problem: flake.fixed is declared (ergostat.yaml:200) and emitted nowhere, so no flake leaves seen; the queue's green runs could clear them, but its unit and browser commands print no PASSED lines (dev/factory.toml:158, :170), so a deleted or renamed flake would count as passed. Change: add `p` to the -r flags of `[suites] unit` and `browser` (on top of the -rfEs that merge-pipeline-browser-names-its-failures gives browser, the same line), checking fac.failed_tests and queue.nowhere (queue.py:198-213) still read the same lines. After a green landing (next to gap.merged, queue.py:842) flakes.green(logs) takes each seen item not quarantined, at most 50, and reads its outcome from the run's unit and browser logs with fac.outcomes: a pass raises green_passes by one (a patch testing the value read), unknown changes nothing (a suite not run in that batch is unknown for its tests), and at `[gates] flake_fixed_after` (default 5, ceiling 50) it writes flake.fixed with fixed_by: green-runs and fixed_on. Every flake.seen through flakes.say sets green_passes to 0, so the count is consecutive, in queue order. A failure here never fails or delays a landing. Done: N consecutive green runs naming the test PASSED fix it; a seen between restarts the count; a test absent from the log never counts; README says how a flake leaves seen. Files: dev/factory.toml, dev/bin/flakes.py, dev/bin/queue.py, dev/README.md, tests/test_queue.py, tests/test_factory.py. Budget: 110 net lines.

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. About 80 net lines outside tests (dev/bin/flakes.py +60, queue.py +12, factory.toml +5, README +9),
within the 110 budget.

Choices made alone, each the most reversible I could see:
- `p` goes first, so the flag is `-rpfEs` (unit and browser). pytest prints the short summary in the order of the -r
  characters, and a failure keeps only the last 2000 characters of its log as `tail`. With `p` last, thousands of
  PASSED lines would push the FAILED lines out of that tail. fac.failed_tests and queue.nowhere read the whole log
  and still see the same lines (test_a_failing_browser_test_is_named runs the browser suite's own options and checks
  this, plus PASSED before FAILED and unit's -r equal to browser's).
- The logs come from each suite's own entry: queue.suites now records `log` on every suite, not only on a failure.
  That is the one way to find the green run's logs after bisecting or excusing.
- flakes.green runs after `ask()` (the gated push asked), not before it, so it cannot delay the landing. It is
  wrapped in queue.greened: any Exception goes to stderr and the landing goes on.
- A test with a FAILED or ERROR line in a green run (only an excused flake, which flakes.say has just set back to 0)
  counts as no pass and changes nothing. Only PASSED with no FAILED or ERROR counts.
- A suite that is red, stopped by a sibling, or whose log is missing says nothing about its tests (unknown).
- `fixed_on` is main's head after the landing (`merged`). `fixed_on` is added to REMAKE_CLEARS, and a remake no
  longer removes a field it is setting (the seen's own `green_passes: 0`).
- `[gates] flake_fixed_after` must be a whole number from 1 to 50; anything else is refused with a ValueError, so
  nothing is counted, never a guessed count. It is read in flakes.py, not through fac.gate, because fac.py is not in
  the Files list.
- The patch's `test` op guards against a writer that skips the lock. Every writer of `green_passes` holds
  run/flakes.lock and green() reads the item again inside it, so no test can open that race window. The test op is
  defence in depth and no test checks it.

Outside the Files list: tests/test_agents.py line 37 pinned `" -rfEs "` in `[suites] browser`. It now pins
`" -rpfEs "` (rerun keeps -rfEs).

Tests run (serial, named_tests.py): the five acceptance tests (test_factory.py:
test_n_consecutive_green_runs_naming_the_test_passed_fix_it, test_a_seen_between_green_runs_restarts_the_count,
test_a_test_absent_from_the_log_never_counts; test_queue.py: test_a_green_landing_counts_each_seen_flake_it_says_passed,
test_a_failure_counting_the_flakes_never_fails_the_landing); all of tests/test_queue.py (19 passed),
tests/test_queue_host.py (12 passed), tests/test_agents.py (all passed except the one below); and twelve flake, queue
and -r tests in test_factory.py. Every one passed. Each acceptance test was seen to fail with its code broken: the
seen reset removed, unknown read as pass, red suites read, the queue's call removed. Not run: the whole of
test_factory.py (it does not fit in one foreground call, and a background run was refused), the full unit suite and
the four browser files (the queue runs those).

Unrelated: tests/test_agents.py::test_a_rerun_is_timed_by_the_suite_that_failed fails when run alone in that file's
order with `ModuleNotFoundError: No module named 'flakes'`. It loads dev/bin/onmain.py, which imports flakes (on
main since regression-flake-writes-hold-state), without dev/bin on sys.path. This change does not touch it. It could
not be run on a main worktree here (`git worktree add` was refused).
