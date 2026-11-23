# merge-pipeline-browser-only-on-its-paths: A batch skips the browser suite only when everything it touches is known not to reach the pages

depends-on: [merge-pipeline-browser-daily-on-main]

## Problem
Every queue run, including each bisect step, runs the four browser files beside the unit suite (queue.py:156; factory.toml:170). That is about 9-10 minutes of 4 CPUs per run (run/queue/*-browser.txt on 2026-11-22). Most batches change no page: of the 30 queue send-backs on 2026-11-22, the conflicting files were almost all under ergostat/spec, ergostat/remote, dev/bin and docs. With the daily main run in place, the owner's direction is to run the browser suite in a batch only when the batch touches what it tests.

## Change
`[suites] browser_paths` in dev/factory.toml lists globs, by default ergostat/web/**, examples/**, tests/fixtures/layout_known.json, tests/fixtures/diagram_sizes.json, tests/layout_*, and the four browser test files. queue.suites runs the browser step only when `git diff --name-only pre HEAD` matches one of them. Otherwise the run records `browser: {not_run: "no browser path changed"}` on suites_queue. rest() (queue.py:230-232) and excused() treat a suite that was not run as finished, never as stopped. An empty list runs browser every time, as today. Bisect sub-runs of a batch use the batch's decision.

## Definition of done
1. A batch touching only dev/bin runs no browser step and records not_run.
2. A batch touching ergostat/web/ runs it, as today.
3. A red unit run in a batch without browser paths never runs browser for rest().
4. `browser_paths = []` runs browser in every batch.
5. The queue's docstring (step 5) and dev/README.md say so, and name the daily main run as the net.

## Files to touch
dev/bin/queue.py, dev/factory.toml, dev/README.md, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_a_batch_without_browser_paths_skips_browser_and_says_so
- tests/test_factory.py::test_a_batch_touching_the_web_runs_browser
- tests/test_factory.py::test_an_empty_browser_paths_runs_browser_always

## Size budget
40 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1. 23 net lines in dev/bin (queue.py +31/-8, onmain.py's docstring reflowed, net 0), budget 40.

- `queue.browser_wanted(cfg, repo, pre)`: `git diff --name-only --no-renames -z pre HEAD` (a move out of a listed path
  counts both paths) matched by `fnmatch.fnmatchcase`, so `*` crosses `/` and `ergostat/web/**` and `tests/layout_*`
  mean what they say. `queue.suites(..., browser=)` takes the decision; not run, the step is left out and
  `suites_queue.browser` is `{not_run: "no browser path changed", counts: "not_run"}`: the `counts` key is the one
  regression-queue-test-counts' `summed()` already reads, so the landed run's sum leaves browser out, neither unknown nor 0.
  The entry is written before the steps run, so a red run always has it and `rest()` (unchanged: an entry with no
  `stopped_by` is finished) never lists browser; `excused()` takes the rest as it was.
- The batch's decision is made once in `land()`, on its first full run (the whole batch, in the checkout), under the
  `counting` lock, and every later full run (halves, the rest of an excused run) is handed it. Prefixes run only
  named tests (`named()`), never the browser step, so they need no decision.
- Choices taken with nobody to ask, each the reversible, fail-safe one (lesson-3): `browser_paths` absent (as in the
  tests' fixture) runs browser always, the same as `[]`; a value that is not a list of non-empty strings, or a diff
  that cannot be read (a missing `pre`), runs it too. The default list is exactly the one in the definition; it does
  not list tests/conftest.py or the page tests' helpers, so a change only there reaches the pages only through the
  daily run on main, the net the docs name.
- Outside the Files list, two docstring/comment lines that would otherwise overclaim (lesson-8): dev/bin/onmain.py's
  "the merge queue runs unit, browser and demo in full either way", and the same sentence twice in dev/factory.toml.
- Tests broken on purpose (lesson-9), each failed and was restored: the halves deciding for themselves
  (`browser=None`) failed test_a_batch_touching_the_web_runs_browser (2 browser runs, not 3); `[]` read as "never"
  failed test_an_empty_browser_paths_runs_browser_always; browser always run failed
  test_a_batch_without_browser_paths_skips_browser_and_says_so; rest() listing a `not_run` suite failed that test's
  direct rest() check (its queue half still held, since the rest run is handed the batch's decision too).
- Run here: the three acceptance tests (3 passed); test_queue.py's three counts tests; the flake-excuse, red-tree
  and suite-watch-command tests (3 passed each). ruff clean on ergostat, tests, scripts. Not run here: the whole unit
  suite and the four browser files (the factory and queue run them). The clone is made from main, with no new commits
  on it, so there was nothing to merge.

Round 2: main (059ff718) merged in; its one conflict, dev/factory.toml's `browser` line, resolved by keeping main's
`-rpfEs` flag and comment (the PASSED lines flakes.green reads) with the branch's "browser on browser_paths" wording
and `browser_paths` list. Checked against main's new `queue.greened`/`flakes.outcomes`: a not-run browser entry has
no `rc` or `log`, so its tests are read as unknown, never as a pass. Run again after the merge: the three acceptance
tests (3 passed); test_a_landed_run_records_each_pytest_suites_counts_and_their_sum,
test_a_green_landing_counts_each_seen_flake_it_says_passed, test_a_green_batch_lands_every_gap (3 passed). ruff clean
on ergostat, tests, scripts (the B023 in dev/bin/plan.py and the E501 in dev/bin/review.py come from main and are not
this branch's). Not run here: the whole unit suite and the four browser files.
