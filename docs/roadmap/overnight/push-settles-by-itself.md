# push-settles-by-itself: A settled push is recorded without waiting for another queue run

depends-on: []

Audit 2026-11-21 (reproduced): when gap A fails in a batch, B lands and the push runs with no other gap approved, nothing starts a queue run, so A stays in `push-pending` indefinitely and the watch counts that as explained.

## Definition of done
A push that ran, failed or was denied is settled within minutes with no approved gap waiting, and the held outcome is applied. A gap in `push-pending` with no pending push is a stuck situation.

## Files to touch
`dev/bin/queue.py`, `dev/bin/watch.py`, `dev/model/landing.yaml`, `tests/test_factory.py`.

## Risks
- lesson-1: settling and a starting queue run must not both apply the outcome.

## Acceptance tests
- `tests/test_factory.py::test_a_push_settles_with_no_gap_approved`
- `tests/test_factory.py::test_a_gap_pending_with_no_push_is_stuck`

## Size budget
40 net lines of code outside `tests/` and `docs/`.
