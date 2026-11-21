# pool-full-keeps-its-rank: a gap told the pool is full is not overtaken by lower-ranked gaps

depends-on: []

Seen on 2026-11-21. The engine leases gaps by rank, so when the machine is near its limit the highest-ranked waiting gap is leased first. `pools.my_turn()` finds no room (`resources.room`), and `implement.py` gives it back with `after="5m"`; `review.py` does the same. When room appears a minute later, that gap is still put off, so a lower-ranked gap takes the slot. At 10:54 the two gaps ranked 1 and 2 had waited about 25 minutes in `fix` while unranked gaps built. There were 27 such give-backs in 12 minutes.

## Definition of done
1. A gap given back because its pool is full is put off for at most 45 seconds, in both `implement.py` and `review.py`.
2. With a free slot and gaps of different ranks waiting, the highest-ranked gap is the one that runs next, including one that was just given back for a full pool.
3. The give-back is still not counted as an attempt.
4. The give-backs do not spin: `implement-when` and `review-when` already hold the blocks shut while no session fits, and a test shows a full machine does not re-lease in a tight loop.

## Files to touch
`dev/bin/implement.py`, `dev/bin/review.py`, `tests/test_factory.py`.

## Risks
- Test through the engine's real dispatch order, not by asserting the `after` value alone.

## Acceptance tests
- `tests/test_factory.py::test_a_pool_full_give_back_waits_under_a_minute`
- `tests/test_factory.py::test_the_highest_ranked_gap_takes_the_next_free_slot`
- `tests/test_factory.py::test_a_full_machine_does_not_release_and_retake_in_a_loop`

## Size budget
10 net lines of code outside `tests/` and `docs/`.

## Where it stopped

The change is built (`after="45s"` in `dev/bin/implement.py` and `dev/bin/review.py`, 3 net lines) and the three
acceptance tests pass, as do `tests/test_factory.py` in full (120 passed, 2 skipped). After it, the factory's `unit`
suite failed three tests, but the tail it gave shows only their positions (`F` at about 5%, 11% and 94%), not their
names. The implementor could not read the suite's full log, and the brief forbids running the whole suite itself.
Every file that touches `implement.py`, `review.py`, the pools or the dispatch was run alone, and all passed:
tests/test_factory.py, test_review.py, test_factory_resources.py, test_factory_sessions.py,
test_factory_knowledge.py, test_factory_times.py, test_factory_join.py, test_factory_manager.py,
test_architecture.py, test_code_health_coverage.py and test_backlog.py. No test or doc outside the branch refers to
the old `5m`. The code was not changed blindly (the reversible choice). Left: the names of the three failures, from
the factory's run, to decide whether they are this branch's or load flakes on main (lesson 13).

Round after that (the second `unit` failure): the tail shows a single `F` at about 34% (and one `x`), where the
first run showed three at 5%, 11% and 94%. Under `-n` the order is not fixed, so the position does not name a test,
but the count and places changed between two runs of the same code, which looks like load. Still no name: the tail
cuts off before the summary, and `.pytest_cache/v/cache/lastfailed` in the worktree is `{}`. Bash was refused at the
implementor's first command (`git log --oneline -4 && git diff main --stat ...`), so this round ran nothing,
committed nothing (this section is left in the working tree, not committed), and changed no code. By reading: the
only test outside the acceptance tests that asserts a give-back's `after` is
`test_a_switch_waits_for_the_runs_under_way` (`"5m"`, tests/test_factory.py:2710). It comes from the drain's nack in
`dev/bin/fac.py:87`, which this branch does not touch. Left: the failing test's name from the factory's full log,
then either a fix here (if it is this branch's) or a report against main (lesson 13).

Round 2 (after main 313f147b was merged in, 1bbe4aee): no code changed. Run here, one file at a time:
tests/test_factory.py (120 passed, 2 skipped), tests/test_review.py and tests/test_factory_resources.py (32 passed),
and `ruff check ergostat tests scripts` (clean). Lesson 9: putting `after="5m"` back in review.py fails
`test_a_pool_full_give_back_waits_under_a_minute[reviewer-...]`. Putting it back in implement.py fails the implementor
case and `test_the_highest_ranked_gap_takes_the_next_free_slot`. Both were restored. The whole unit suite was not run
here (the brief leaves it to the factory), so the earlier unnamed `unit` failures are still unnamed. If they come back,
the factory's full log must name them. This branch changes only the two `after` values, and by reading no other test
depends on them.

Round 3 (the third `unit` failure, one `F` at about 19%): `.pytest_cache/v/cache/lastfailed` in the worktree named
`test_a_pool_full_give_back_waits_under_a_minute[implementor-...]` and
`test_the_highest_ranked_gap_takes_the_next_free_slot`. Those are also the two that round 2's lesson-9 check broke on
purpose, so the cache does not prove they were the `unit` failure. By reading, this branch's own test harness
(`Slots`) has a load race. When a played run ends, `Dispatcher._work` pokes the engine. With no loop running, the poke
runs a whole `evaluate()` in the run's thread, after `running` is cleared, so `Slots.tick`'s wait can end before that
pass does. Its first pass is a full one: it steps `implement-when` / `review-when` with no sensor readings and pops the
gate signal the next tick has just set. The dispatcher then reads the block as commanded to 0 and takes nothing. Under
load the pass is slower and overlaps more often, which fits both tests named and a failure that moves between runs.
Fix (tests only, no bound changed): `Slots` stubs `e.poke`, since the test is the pass and sets the gate at each tick.
The dispatch is still the engine's own. The race was not reproduced here (a profiling plugin under /tmp was refused),
so the fix is shown by reading. Run here: tests/test_factory.py (120 passed, 2 skipped), ruff clean. Separately, each
test process spends about 60 s once in `Factory.__init__` reading ergostat.yaml (the extremes check). That is main's
fixture, not this branch's.
