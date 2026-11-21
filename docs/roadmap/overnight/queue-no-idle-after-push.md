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

## Where it stopped

Built; the acceptance tests and `tests/test_factory.py` pass. The fast-suite `unit` run failed on one test this branch
does not touch: `tests/test_index_files.py::test_two_processes_one_tidying_never_corrupt_an_index_another_has_open`.
Its spawned children `import queue` (multiprocessing) and get `dev/bin/queue.py` instead of the standard library
(`cannot import name 'Empty' from 'queue'`), because tests on main put `dev/bin` on `sys.path` and never take it off
(`tests/test_backlog.py:24` `intake()`, `tests/test_factory.py:2830`). It depends on the order: it passes alone, and
fails when run after `tests/test_backlog.py` alone (`pytest -p no:randomly tests/test_backlog.py` then the test),
with no file of this gap involved. Under lesson-13 it is reported, not fixed here; the fix (take `BIN` off `sys.path`
after the import, as `tests/test_factory_knowledge.py` does) belongs in its own gap.

Round 2: main (b24eb901) merged in. The conflict in `dev/bin/queue.py` kept both sides: main's `settleable()`,
`settle_alone()`, and its failed-push path (`then` released after `block()`), plus this gap's `Waits` and the
`Waits(...)` return for a held, requested or approved push. After the merge the three acceptance tests,
`tests/test_factory.py` (119 passed, 2 skipped) and ruff pass. Checked that the tests can fail: with `"1m"` changed to
`"10m"`, the waiting-push and next-batch tests fail; with `"10m"` changed to `"1m"`, the blocked-queue test fails.
Round 1's non-blocking findings: the `Waits(str)` subclass stays, because the change is meant to stay a few lines in a
file that often conflicts, and `test_a_waiting_push_puts_gaps_off_for_a_minute` fails if anything wraps it. The
next-batch test still does the dispatcher's timing by hand and does not drive `ergostat/leases/dispatch.py` end to end.
That is a narrower claim, written down here rather than widened.

Round 3: the merge of main (b24eb901) was already committed (024ff190), so there was nothing left to resolve. The
`unit` tail I was given names no failing test. On this tree `tests/test_factory.py` passes (119 passed, 2 skipped) and
ruff is clean. Run in a fixed order, `tests/test_backlog.py` followed by
`tests/test_index_files.py::test_two_processes_one_tidying_never_corrupt_an_index_another_has_open` fails as before
(`cannot import name 'Empty' from 'queue' (/work/dev/bin/queue.py)`). That is the `sys.path` leak on main described
above, and this branch touches neither file. Running the same pair on a clean worktree of main was refused
(`git worktree add -q --detach /tmp/mainchk main && ...`), so the claim that main fails too rests on reading the code,
not on a run. Under lesson-13 the leak is left for its own gap; nothing in this gap's code needs fixing.
