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
