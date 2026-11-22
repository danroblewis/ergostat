# a-lease-end-is-never-dropped: a run's lease end waits its turn and is retried, never left to expire

depends-on: []

`ergostat/leases/dispatch.py:381` `Dispatcher.finish` takes `self.ends` with `timeout=self.e.lock_wait` and raises `TimeoutError("another end of a lease is wedged")` when another end holds it. Every lease end is serialized under that lock, and `_finish` folds the item from the record (`its.one`), which on the factory's record takes seconds under load. On 2026-11-22 this dropped four lease ends (02:11 an implementor's and a reviewer's; 05:45 the merge queue's). The merge queue's run had merged its gap, but its lease stayed held until its 30-minute TTL ran out. The queue's pool is 1, so nothing merged for 30 minutes while 30 gaps waited.

## Definition of done
1. A run's end is never dropped because another end is under way: `finish` waits for its turn, retrying with backoff until the lease's own TTL is near, and only then gives up, saying so with the item and the run.
2. While waiting, it does not hold the dispatcher's main lock, so takes and looks go on.
3. The fold `_finish` needs is read once and not under `self.ends` when that can be done safely (the fence check stays under it), so one end holds the lock for milliseconds, not seconds.
4. A run whose end was given up raises a pipeline situation naming it, so the item does not sit leased silently.
5. SPEC's lease section says so.

## Files to touch
`ergostat/leases/dispatch.py`, tests under `tests/` (the leases tests), `docs/SPEC.md`.

## Risks
- lesson-1: two ends of one lease must never both write: the fence check under `self.ends` stays.
- lesson-6: an end retried after the engine stops must still end (stopping is not a reason to drop it).

## Acceptance tests
- two runs ending at once, the first's fold slowed to past `lock_wait`: both leases end, neither raises
- a slow end does not block a take or a look on another block
- an end that cannot complete before the TTL raises a situation

## Size budget
50 net lines of code outside `tests/` and `docs/`.

## Also: a finished run's lease is never renewed (seen 06:23)

After the merge queue's run ended (its gap merged at 05:45 and pushed at 05:46, its process gone), the watchdog renewed its lease at 06:23 on "activity" (`Dispatcher.look`, `ergostat/leases/dispatch.py:469`), so the lease did not expire and the queue's only slot stayed held for an hour. A lease whose run has ended (no live process for the run id this engine started, or the run's end attempted) is never renewed on activity: it is ended (or expires on its first look). Acceptance: a run that ended with its lease end failed does not hold the lease past one watchdog pass.
