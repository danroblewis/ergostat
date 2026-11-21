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
