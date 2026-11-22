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

## Where it stopped

Built, round 1: every point of the definition and the 06:23 addendum, 38 net lines in `ergostat/leases/dispatch.py`
(54 added, 16 removed), and SPEC §9.5 (*Renewal is observed*, and a new paragraph *Ends wait their turn*).
Acceptance tests, in `tests/test_lease_end_turns.py`:
- `test_two_runs_ending_at_once_the_first_s_fold_slowed_past_lock_wait_both_end`
- `test_a_slow_end_does_not_block_a_take_or_a_look_on_another_block`
- `test_an_end_that_cannot_complete_before_the_ttl_raises_a_situation`
- `test_a_run_whose_end_failed_does_not_hold_the_lease_past_one_watchdog_pass` (the addendum's acceptance)

Each was seen to fail with the code it guards broken: giving up on the first `lock_wait` (the old behaviour) fails the
first two; reading the item only under `self.ends` fails the first (the second end then ends after the first, not
while the first reads); holding `self.lock` while the end sleeps between tries fails the second; skipping the
watchdog's check of `ending` fails the last two (the lease is renewed on activity).

Choices made alone (the most reversible):
- The fence check under `self.ends`: the item is read once before the lock (the record's last seq noted first); under
  the lock one indexed query asks whether any `ergostat.lease.*` event about the item came after that seq, and only
  then is the item read again there. So two ends of one lease never both write (lesson-1), and the common end holds the
  lock for one query and one write. A nack's "a dead letter now" wording is read after the lock is let go.
- "Until the lease's own TTL is near" is until one `lock_wait` before the lease's `expires` as read; the pause between
  tries doubles from 0.05 s to at most 5 s. The pause is `time.sleep`, not the stop's wait, so ergostat stopping does
  not cut it short (lesson-6). Consequence: close()'s give-back can now wait, with another end wedged under the lock,
  up to the remaining TTL of its leases (before: one `lock_wait`). Since an end now holds that lock only for a query
  and a write this should be rare; it is said here in case a review wants close's give-back bounded instead.
- The "pipeline situation" is carried as the dispatcher's standing error (`failing`, the heartbeat's
  `dispatch_error`), the only channel from the engine to `dev/bin/live.py` health and `dev/bin/watch.py`'s `dispatch`
  condition, so no file outside the definition's list changed. `failing` is now a property: a given-up end, for
  `HOLD` (an hour) after it was given up, timed from when the end was first tried (so the watch's two-minute rule is
  usually met already), else the looks' error as before (`looks_failing`). The watch's own wording ("the dispatcher
  has failed every look for N min: ...") is followed by the end's text, which names the run and the item. The test
  checks the heartbeat and `live.dispatch_failing`; the step from there to a raised situation is
  `tests/test_one_bad_link.py::test_a_repeated_dispatcher_error_raises_a_situation`.
- "A run that has ended" is read as "its end was tried by this engine and has not completed" (`ending`: set at every
  `finish`, cleared when it completes). The watchdog's first look past the expiry of such a lease tries the end once
  more (one `lock_wait`), and when that fails it expires the lease at once, without the grace of a second look. A run
  whose finish was never called is left to the old path, and so is a lease held by another engine's run.
- An expiry the watchdog records between an end's check under the lock and its write still makes the fold refuse that
  end, as on main (the watchdog's expiry does not take `self.ends`); unchanged here.

Not run: the whole unit suite, the four browser files (no page changed) and demo_check (no example touched): the
factory runs them. Run here, each passing: `tests/test_lease_end_turns.py`, `tests/test_leases.py`,
`tests/test_one_bad_link.py`, `tests/test_run_budget.py`, `tests/test_queue.py`, `tests/test_resilience.py`,
`tests/test_lease_kill.py`, `tests/test_lease_refused_cost.py`, `tests/test_leased_workspaces.py`; ruff clean. Local
`main` merged in (already up to date; there is no origin here).

### Round 2

The one finding of round 1 (dispatch.py:167-172, lesson-3: a given-up end hid the looks' errors for an hour and stood
an hour after its lease was ended), answered in each of its parts:
- The looks' standing error is now reported first, with its own text and its own `since`; a given-up end is said only
  while no look is failing. `test_an_end_that_cannot_complete_before_the_ttl_raises_a_situation` now records a look
  error after the give-up and checks that `failing` is that error with a fresh `since`, then the end again once the
  looks are clean. Seen to fail with the old order (the given-up end returned first).
- An entry in `dropped` no longer has a fixed hour. It stands while its lease is held, however long that is. It is
  marked let go when its end completes (`finish`), or when a whole watchdog pass finds no lease held by its run (ended
  or expired, here or elsewhere). After that it stands for `HOLD`, now 360 s, then `failing` removes it. 360 s is one
  pass of the pipeline watch's 5-minute `broken` sensor (`dev/model/manager.yaml`) plus a minute: "what is needed for
  the watch to see it once". New test
  `test_a_given_up_end_is_said_only_while_its_lease_is_held_and_one_watch_pass_after`: with the lease held it is said
  at 10×`HOLD` later; once the watchdog has ended the lease it is marked let go; `HOLD` after that, `failing` is None and
  `dropped` is empty. Seen to fail with the `finish` marking removed, and with the `HOLD` check skipped. The round-1
  test above now also checks that the watchdog's next pass after the expiry marks the entry let go. Seen to fail with
  the pass's marking removed.
- SPEC §9.5 *Ends wait their turn* now says so: held, then 6 minutes after a pass finds it let go; a look's own error
  is said first and never hidden.

Choice made alone (the most reversible): the watchdog's expiry in `look` does not mark the entry let go directly. Only
a later pass that reads the lease as not held does, because that expiry can be refused (renewed meanwhile), and
clearing the situation on a refused expiry would fail open. So the situation stands one watchdog pass (about a
second, `EVERY`) longer than strictly needed. The watch's wording ("failed every look for N min") still comes from
`dev/bin/live.py`, outside this gap's files, as in round 1.

Size: 49 net lines in `ergostat/leases/dispatch.py` (66 added, 17 removed), within the 50 budget.

Run here, each passing: `tests/test_lease_end_turns.py` (5), `tests/test_leases.py`, `tests/test_one_bad_link.py`,
`tests/test_lease_kill.py`, `tests/test_lease_refused_cost.py`, `tests/test_leased_workspaces.py`, `tests/test_queue.py`,
`tests/test_resilience.py`, `tests/test_run_budget.py`; ruff clean; local `main` merged (already up to date). Not
run: the whole unit suite, the four browser files (no page changed) and demo_check (no example touched).
