# queue-empty-batch-says-why: a queue run whose batch comes back empty ends with a recorded reason, not silently

depends-on: []

## Definition of done

1. In dev/bin/queue.py take(), when picks() returns an empty batch after gap.queued has been said, the run's own gap gets a recorded outcome. It is nacked with a reason naming what emptied the batch: its dry merge failed only with batch-mates on both walks, or it was sent back, or a dry merge named no file. Today the code returns 0 and the lease just ends (seen: gap/library-trust-folders went approved -> leased -> queued -> approved 26 times in 10h, with 14 approved gaps all stuck the same way at 17:13).
2. Such a run is counted per gap (queue_attempts or similar) with a ceiling. Past the ceiling the gap is sent back with the reason as a finding instead of being taken again forever (lesson-4).
3. picks() returns why it is empty, so the reason comes from the walk itself and is not guessed afterwards.
4. docs/ and dev/README.md say what an empty batch does.

## Acceptance tests

- tests/test_queue.py::test_an_empty_batch_nacks_its_gap_with_the_reason
- tests/test_queue.py::test_a_gap_whose_batch_is_empty_past_the_ceiling_is_sent_back
- tests/test_queue.py::test_picks_says_why_its_batch_is_empty

## Size budget

60 net lines outside tests and docs.
