# queue-picks-mergeable: The queue fills each batch with gaps that merge

depends-on: []

Measured 2026-11-21: batches of 3 landed 1.8 on average. All 4 conflicts were already conflicts with the batch's base, so a dry merge would have caught them at no suite cost. 7 of 24 approved gaps conflict with main.

## Definition of done
- The queue walks approved gaps in rank order, dry-merging each onto the batch so far (`git merge-tree --write-tree`), until the batch is full.
- A conflict with main sends the gap back at once and takes no slot. A conflict only with a batch-mate leaves it approved, with no failed gate.

## Files to touch
`dev/bin/queue.py`, `tests/test_factory.py`, `dev/README.md`.

## Risks
- lesson-1: the tree dry-merged is the tree tested.

## Acceptance tests
- `tests/test_factory.py::test_a_conflicting_gap_takes_no_batch_slot`
- `tests/test_factory.py::test_a_batch_mate_conflict_is_not_a_failed_gate`
- `tests/test_factory.py::test_batch_keeps_rank_order_among_mergeable_gaps`

## Size budget
60 net lines of code outside `tests/` and `docs/`.
