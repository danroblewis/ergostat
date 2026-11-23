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
