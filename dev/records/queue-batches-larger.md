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

## Where it stopped
Built in round 1; about 35 net lines of code (queue.py +34, most of it the bisect loop re-indented inside its
`try`; pools.py -2; factory.toml +3), plus 3 in dev/README.md.

Choices made alone (the most reversible):
- The allowance is `[pools] batch_minutes`, 120 by default, capped at 150 (`ALLOWANCE_MOST` in queue.py). A value
  outside 0..150, NaN included, counts as 150. It is measured from the queue process's start, so the lock and
  quiet-machine waits count too. It is checked before every suite run and every named rerun, so a run lasts at most
  the allowance plus one suite run. Point 2's "never hits 3 h" holds only while a single suite run takes under 30
  minutes. Nothing here bounds a suite run that hangs.
- `batch_max` has no hard ceiling above it: the batch adds serial git merges, not processes, and the allowance bounds
  its suite runs.
- A prefix lands at the allowance only if it was proven by a full green run. A prefix green only on the named tests
  lands nothing.
- The run's own gap, when it is among those given back, is nacked uncounted (`after` 1m). Others stay `approved`. If
  others landed, the push is still asked under the own gap's lease (`fenced: false`). The own gap does not wait at
  `push-pending`, since it has no outcome to hold back.
- The record is each gap's `queue_runs` entry: `tried`, `landed`, `given_back`. "given_back" means sent back to
  `approved`, uncounted. It is not `gap.sent-back`, which goes to `fix`.

Not run here: the whole unit suite and the four browser files (the factory runs them under the watchdog); the clone
has no origin/main to merge, and local main is already in the branch.
