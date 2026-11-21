# queue-batches-larger: the merge queue tests up to 8 commits together, as many as can combine and pass

depends-on: []

The owner (2026-11-21): the merge gate "should test multiple commits at the same time", bisecting on failures and letting "through as many commits as can be combined and are passing". The batch is capped by the constant `BATCH_MOST = 4` in `dev/bin/pools.py`, whose comment sizes it by the 3-hour run timeout in the worst case of every merge failing. With full suites now only in the queue, it is the factory's main test step.

## Definition of done
1. The most a batch may be is `[pools] batch_max` in `dev/factory.toml`, default 8, with no separate constant below it. `pools.py set batch N` respects it.
2. A run that has used more than its time allowance stops bisecting: what is proven green lands, the rest go back to `approved` uncounted, and the next run takes them. A batch of 8 with every merge failing can never hit the block's 3-hour timeout.
3. `picks()` still fills the batch by rank with gaps that merge cleanly together.
4. The run's record says how many it tried, landed and sent back.

## Files to touch
`dev/bin/pools.py`, `dev/bin/queue.py`, `dev/factory.toml`, `tests/test_factory.py`.

## Risks
- A run stopped at its allowance must never push an unproven prefix.

## Acceptance tests
- a batch of 8 all green lands in one run
- one bad commit of 8 is found, and the other 7 land
- a run past its time allowance lands only what is proven and gives back the rest uncounted

## Size budget
60 net lines of code outside `tests/` and `docs/`.
