# merge-pipeline-browser-names-its-failures: The browser suite and the rerun print FAILED lines, so their failures are named, excused and triaged

depends-on: []

## Problem
dev/factory.toml:170 runs the browser suite with `-q -rs`, and :180 runs the rerun with `-q -rs`. `-r` replaces pytest's default `fE`, so no FAILED or ERROR line is printed, and fac.failed_tests (dev/bin/fac.py:556-561) finds none. The unit suite was fixed for this already (factory.toml:158-160, `-rfEs`). Every browser red in the record carries a tail and no test: 5 queue-failed events from 2026-11-20 to 2026-11-22, among them the-module-map-is-read-and, job-person-steps, proposals-drawn-dashed-in-both-diagrams-continued (twice) and split-verified-join-2. As a result:
- it is never excused as a flake (queue.py:217-222);
- it is bisected with full runs of every suite (queue.py:698);
- triage says "named no test" and sends it to fix (triage.py:60).

## Change
`browser` and `rerun` use `-rfEs`, with a comment like the unit suite's. Add a test that each suite command in dev/factory.toml that fac.failed_tests reads (unit, host, build, browser, rerun, alone) keeps f and E in its -r, or has no -r at all.

## Definition of done
1. A browser run with a failing test yields that test from fac.failed_tests.
2. queue.suites's skip count (`^SKIPPED`, queue.py:111) and nowhere() still read the same skips.
3. The config test fails if a later edit drops f or E.

## Files to touch
dev/factory.toml, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_every_suite_fac_reads_prints_failed_lines
- tests/test_factory.py::test_a_failing_browser_test_is_named

## Size budget
0 net lines of code (configuration and tests).

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
