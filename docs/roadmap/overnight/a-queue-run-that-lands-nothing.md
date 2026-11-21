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

## Where it stopped

Built, round 1. Nobody could be asked, so these choices were taken alone, the most reversible way:

- **A sent-back own gap is not nacked.** When the walk sends the run's own gap back (not merged, or a conflict with
  main, `(git named no file)` among them), the `gap.sent-back` already said is its recorded outcome, and picks() names
  it (`it was sent back: ...`). A nack there would end the lease to `back`, which is `approved`, over the sent-back.
  That would bring back the very loop this gap ends. So only the other reason, a dry merge that failed only with
  batch-mates on both walks (`(no file)` when git named none, the shape the 26 runs had), is nacked: uncounted by the
  lease, `after` 10m, with the reason.
- **The count is `empty_batches`, not `queue_attempts`.** `queue_attempts` is a sum over every queue run, and
  measure.py and triage.py read it. The new field is `{head, n}`, kept per reviewed commit, so a gap made again with a
  new commit counts from nothing (lesson-5). The ceiling is `EMPTY_MOST = 3` in queue.py, a constant and not a
  setting, so no config can raise it. The third empty run sends the gap back through refuse(), as a failed gate, so
  the kill rule bounds the build-review-queue loop too, and n goes back to 0. refuse()'s park wording now says
  "the last, in the merge queue: ..." in place of "a conflict in the merge queue", since its finding may not be a
  conflict.
- **docs/**: no page in docs/ outside the roadmap describes the factory's merge queue; dev/README.md is where it is
  documented for human readers. The empty batch is described there (after the batch's walk), and in queue.py's
  docstrings. No new docs page was added.
- With today's dry() (a conflict always names a file, or `(git named no file)`), the second walk puts the own gap
  first onto main, so it either merges or is sent back. The "batch-mates on both walks" branch is reachable only
  through a dry merge that reports no conflicting files. The acceptance tests stand that in for git (`NO_FILE` in
  tests/test_queue.py).
- The tests take 45 to 60 s each in this container. test_factory.py's queue tests, unmarked, take the same here
  (test_batch_of_one_is_todays_queue: 61 s), so the new ones follow them and are not marked `slow`.
