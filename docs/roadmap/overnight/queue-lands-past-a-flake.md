# queue-lands-past-a-flake: a batch whose only failures pass alone on the same tree lands, and the flake is recorded

depends-on: []

The owner (2026-11-20): "we can disable the flakey tests, or run them without blocking and review them after", and "the merge test suite should not fail for reasons other than the sum of the commits". On 2026-11-21 the queue landed nothing for over an hour: a single timing failure in a full suite makes `land()` run `named()`; the test passes alone on the whole red tree; the batch is then bisected with every suite, so one flake costs two or three more passes of 8 to 12 minutes. Between 12:44 and 13:44, five different tests did this.

## Definition of done
1. When a red run named its failed tests and each one passes when run alone on that same red tree (`named()`), rerun them once more. If they pass both times, the batch is green and lands, with no bisect.
2. Each such test is recorded where flakes are recorded (its flake item, or `failed_tests` beside the merge), with the run, the suite and that it passed alone, so that it can be reviewed after and its count is visible.
3. A test that fails alone on the red tree, in either rerun, bisects exactly as now.
4. A red run that named no tests (a killed or timed-out suite) bisects exactly as now.
5. `tests/test_page_polling.py` is never excused this way: its failure is handled as a real failure (`dynamics-open-dom-growth` is finding out if it is a leak).
6. No more than 3 tests may be excused in one run: more than that is not a flake, and it bisects.

## Files to touch
`dev/bin/queue.py`, `tests/test_factory.py` (or the file holding the queue's bisect tests).

## Risks
- This can land an order-dependent bug. That is why each excused test is recorded, why the count is capped, and why a test that fails alone never lands.
- lesson-3: a rerun that cannot be read or has no PASSED line counts as failed.

## Acceptance tests
- a batch whose one failed test passes alone twice lands, with no bisect, and the flake is recorded
- a test that fails alone on either rerun still bisects
- four failed tests that each pass alone still bisect
- a page-polling failure is never excused
- a run that names no tests still bisects

## Size budget
50 net lines of code outside `tests/` and `docs/`.
