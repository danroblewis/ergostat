# red-batch-fast: A red batch stops early and bisects on its failing tests

depends-on: [queue-picks-mergeable]

Measured 2026-11-21: red runs and bisection cost 47 of 480 minutes, and all 6 red runs were in the unit suite.

## Definition of done
- The first suite failure stops its sibling suite.
- Bisection reruns only the named failing tests on each prefix. A failure naming no test uses today's full bisect.
- **Whatever lands still has a full green run on its exact tree.**

## Files to touch
`dev/bin/queue.py`, `tests/test_factory.py`, `dev/README.md`.

## Risks
- lesson-1, lesson-3: a shortened bisect never counts as the green run.

## Acceptance tests
- `tests/test_factory.py::test_a_failed_suite_stops_its_sibling`
- `tests/test_factory.py::test_bisect_reruns_only_the_failing_tests`
- `tests/test_factory.py::test_a_failure_naming_no_test_bisects_in_full`
- `tests/test_factory.py::test_nothing_lands_without_a_full_green_run`

## Size budget
120 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1. All four acceptance tests are written and pass. Each guarded line was broken in turn and its test
failed: the sibling stop removed, the bisect run in full, a named run with no tests, a named run that cannot tell
read as green, and a prefix landed on a named-only green.

Choices made alone (the most reversible one each time):
- The named tests run through `[suites] rerun` (serial, `-rA`, with Playwright, so browser tests work too), the
  command flake triage already uses. No new setting.
- A named step is red when one of the tests says FAILED or ERROR. It is green only when the run exits 0 and every
  named test says PASSED. Anything else (a test not on that prefix, which pytest exits 4 on, or a run that never
  started) runs that step with every suite, as today. So a gap whose new failing test is in a file the earlier
  prefixes already have gets no saving on those steps. It costs what it costs today, never less safety.
- A prefix that was green on the named tests only does not land. It is merged again with the merges after the
  failing one, and they all land only on the next full green run of that tree. The failing gap's `pre` is then the
  first try's commit. It may not be on main, but it stays in the checkout with the same tree (tested).
- A sibling stopped after the first failure is recorded as `stopped_by` that suite, and its own result is not judged.
  When both fail at almost the same moment, the one that finished first is reported, not unit by rule. The
  existing `test_the_queue_runs_unit_and_browser_at_once_and_reports_the_first_failure` asserted "the first, in
  order" with a tie (both slept 1 s). It now gives unit a 4 s head start and asserts that browser is stopped.

Size: about +35 net lines in `dev/bin/queue.py`, against 120.

Not run here: the whole unit suite and the four browser files (the factory runs them under the watchdog). There is
no `origin/main` ref in this clone, so main could not be merged in again (lesson-7). The merge queue must do it.

Round 2, answering review/red-batch-fast-1 finding by finding:
- (blocking) Named bisect assumed the tests fail alone. Before bisecting, the named tests are now rerun alone on the
  whole red tree (`heads[-1]`). Only if one says FAILED/ERROR there does the bisect run on them (on the tests that
  failed in that rerun). If they pass there, or the rerun cannot tell, the bisect runs every suite, as today. A batch
  of one skips this rerun, since it has nothing to bisect. New test
  `test_a_named_rerun_green_on_the_red_tree_bisects_in_full`: the rerun says PASSED for everything, and r (not the
  last merge, s) is blamed. With the check undone (`full = red`), it failed: two `gap.queue-failed`, s blamed.
- (wording) The run bound. A named step that falls back now counts as two runs in `batch_runs`. The docstring and
  README say at most `2 + 2 ceil(log2 m)` runs per failing merge: the red run, the rerun on its tree, then each step.
- (pre after a named-only green) The failing gap's `pre` is now `base`, main's head before that batch. No commit of
  the named-green prefix lands, so pre is always a commit main holds. Its quarantine is main's, and garbage
  collection cannot prune it. The price: triage then reruns the gap on main without its batch-mates. If the failure
  needs a batch-mate, triage sees a pass and spends a flake retry. Nothing lands on that, because the gap goes back to
  the queue, and that still needs a full green run. I chose this because it leaves triage.py alone (it is outside
  the files to touch). `test_bisect_reruns_only_the_failing_tests` asserts that pre is an ancestor of main with the
  pre-batch tree. With `onto = base` undone, it failed.
- (not run by the reviewer) Run here, see below.

Size: about +45 net lines in `dev/bin/queue.py` in all, against 120.

Run here: `tests/test_factory.py` in full (102 passed, 2 skipped: the Docker tests, no Docker in this container);
ruff clean. Not run here: the whole unit suite and the four browser files. There is still no `origin/main` ref, so
main was not merged in again (lesson-7). The merge queue must do both.
