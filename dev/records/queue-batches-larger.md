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

Round 2 (the fix round; it replaces two of the round 1 choices above: the value out of range, and no ceiling). Now 54
net lines of code (queue.py +49, pools.py +2, factory.toml +3), within the 60. Each finding of review 1:
- Blocking, the give-back with no end: a run that settled none of its batch (all given back, none landed, failed
  or sent back) leaves `cap` in run/queue.json, half its batch and at least 1. The next run takes at most that many,
  and the first run that settles any gap clears it. The cap is read and written under the queue's lock (take()). A
  cap that is not a positive count gives a batch of 1. A batch of 1 is one suite run, so it settles its gap
  whenever that run begins inside the allowance. Test:
  test_a_run_out_of_time_before_its_first_finding_halves_the_next_batch (the reviewer's example: a bad, 31-minute
  runs, 120 allowed. Run 1 gives back all 8; run 2 takes a..d and finds a). Still left: when the waits alone use up
  the allowance before the first suite run, nothing can be learned and the gap goes back uncounted again. That is a
  busy machine or lock, not the bisect's own steps. Counting it against the gap would blame the gap for the machine.
- batch_max with no ceiling: `BATCH_CEILING = 32` in pools.most(), far above 8, so set and run time are both held to
  it (test_the_batch_s_most_is_batch_max_default_8).
- An out-of-range batch_minutes counting as 150: now refused. A value of 0 or less, over 150, NaN or not a number
  makes the run take no gap and give its lease back uncounted, saying why
  (test_a_time_allowance_out_of_range_is_refused).
- The 3 h claim: dev/README.md narrowed. The timeout is reached only by a suite run begun inside the allowance that
  lasts past it (over 60 min at 120, 30 at 150), and nothing bounds a hung suite run. The dry merges in picks()
  count against the allowance, but they come before the first clock check. Still no test shows a suite run reaching
  3 h.

Broken to watch the new tests fail: the cap not read (run 2 tries all 8 again), the cap not halved, a bad cap read
as the full batch, the ceiling removed, and only negative allowances refused. Each failed its test.
Run: tests/test_factory.py whole (133 passed, 2 skipped for want of Docker), ruff on ergostat tests scripts. Not run:
the unit suite and the four browser files (the factory runs them), and no origin/main in this clone to merge.

Round 3 (the merge of main b4639301, which conflicted in dev/bin/queue.py). Main added the flake excusal
(excusable(), excused(): a red run's 1 to 3 named tests each passing alone twice on the red tree, then the suites it
did not finish). Both kept: the excusal sits inside the branch's `try`, so its named reruns and its `only` run are
checked against the allowance like every other run (run() takes main's `only` and still calls go() first). Out of
time during the excusal, no prefix has been proven by a full green run (lo is 0), so nothing lands and the batch goes
back uncounted. Now 55 net lines of code against main (queue.py +50, pools.py +2, factory.toml +3), within the 60.
Run: tests/test_factory.py whole (142 passed, 2 skipped), ruff on ergostat tests scripts. Not run: the unit suite and
the four browser files (the factory runs them). No test runs out of time inside the excusal.

Round 3, after the factory's unit run failed. The tail it gave names no failing test: two "bringing up nodes...", one
line of 59 passes and a skip, then nothing, no FAILED line and no summary. That reads as a run cut short (killed or
timed out), not a test failing. The merge of main was already committed (29e38dfc), with no conflict markers left.
Every test file that loads dev/bin/queue.py or pools.py, or reads dev/factory.toml or dev/model, passes when run alone
here: tests/test_factory.py (142 passed, 2 skipped), test_queue.py (5), test_agents_drop.py (3), test_identify.py,
test_mended.py and test_review.py (36 together), and test_factory_resources.py, test_agents.py,
test_code_health_simplifier.py and test_code_health_coverage.py (36 together). No code was changed in this round,
since no failure could be found to fix. Refused here: test_factory.py under `scripts/suite_watch.py` with `-n 8`, and
the whole unit suite run serially, so the failure was never reproduced. Left: the factory's full unit output (or a
rerun of it) to name the failing test. If no test fails there, the cut-short run was the machine, not this branch.
