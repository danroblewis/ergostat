# queue-no-idle-after-push: a push waiting for approval no longer puts every approved gap off for ten minutes

depends-on: []

Measured on 2026-11-21: over 23 queue runs in 7.4 h the merge queue sat idle for 2.76 h (37%) with up to 25 gaps approved; 13 of 22 gaps between runs were over 5 minutes, and four were almost exactly 10. The cause is `take()` in `dev/bin/queue.py`. Seconds after a batch asks to push, before the `push-waiting` sensor (read once a minute) has seen it, the engine leases each approved gap to the queue. `settle()` answers that the push is `requested`, and `fac.nack(..., after="10m", count=False)` puts each of them off for ten minutes. The queue then cannot start when the push is approved until a gap is newly approved or the ten minutes pass.

## Definition of done
1. A gap given back because the last push is still held, requested or approved is put off for at most 1 minute.
2. A queue that is `blocked`, or any other reason `take()` gives back a gap, keeps its 10 minutes.
3. Once the push has run, the next batch starts within about 2 minutes while gaps are approved, without any gap being newly approved.
4. Being given back this way is still not counted as an attempt.

## Files to touch
`dev/bin/queue.py`, `tests/test_factory.py`.

## Risks
- A short delay must not spin: while the push waits, the `push-waiting` sensor holds the block shut, so test that the gaps are not re-leased in a tight loop.
- `queue.py` is conflict-prone: keep the change to the few lines around `take()`.

## Acceptance tests
- `tests/test_factory.py::test_a_waiting_push_puts_gaps_off_for_a_minute`
- `tests/test_factory.py::test_a_blocked_queue_still_puts_gaps_off_for_ten_minutes`
- `tests/test_factory.py::test_the_next_batch_starts_once_the_push_has_run`

## Size budget
15 net lines of code outside `tests/` and `docs/`.
