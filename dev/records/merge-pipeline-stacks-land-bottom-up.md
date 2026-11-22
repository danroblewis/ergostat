# merge-pipeline-stacks-land-bottom-up: The merge queue lands a stacked gap only with or after its base, and never without it

depends-on: [bisect-tests-main-itself]

## Problem
A stacked branch holds its base's reviewed commits. picks() (queue.py:505-558) and land() (queue.py:635-729) see only each gap's reviewed commit. Taken alone, a stacked gap would land its base's work under its own name, and the base would later merge as nothing. In a red batch, the merges after a failing one are merged again onto the green prefix (queue.py:718-722). A descendant of the failing merge would then bring the failing commit back. This gap makes the queue safe for stacked gaps. It reads the field `stacked_on: [{gap, sha}]` that the implementor writes.

## Change
- picks(): a gap whose stacked_on names a gap not merged on main (its sha not an ancestor of pre) brings that base in below it, bottom-up (recursively). The base must be approved and held by no run. A base that is not approved, or a stack that does not fit the batch cap n with the run's own gap, gives the run's own gap back uncounted (after 10m) with the reason. It is never counted towards EMPTY_MOST (queue.py:561-580). A stacked batch-mate whose base cannot come along is skipped and stays approved.
- land(): when a merge is blamed (queue-failed), every later merge in the batch whose stacked_on reaches it (at any depth) is given back to approved uncounted. It is never merged again onto the green prefix.

## Definition of done
1. Base A and stacked B, both approved: a run on B tests and lands A, then B, in that order, in one batch.
2. B whose base A is in fix is given back uncounted, with the reason. Its empty_batches is unchanged.
3. A batch where A fails: B is given back to approved, and the green prefix lands without A's or B's commits (checked by the pushed tree).
4. A stack of 3 with a batch cap of 2 gives the run's own gap back uncounted, and the bottom base lands in its own run.
5. A batch with no stacked gap behaves exactly as today: a test pins it.
6. The queue's docstring (step 3, item 6) says so.

## Files to touch
dev/bin/queue.py, tests/test_factory.py.

## Acceptance tests
- tests/test_factory.py::test_a_stacked_gap_brings_its_base_into_its_batch_below_it
- tests/test_factory.py::test_a_stacked_gap_whose_base_is_in_fix_is_given_back_uncounted
- tests/test_factory.py::test_a_failing_base_gives_its_descendants_back
- tests/test_factory.py::test_a_stack_deeper_than_the_cap_gives_the_own_gap_back

## Size budget
90 net lines in dev/bin.

Area: merge-pipeline. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
