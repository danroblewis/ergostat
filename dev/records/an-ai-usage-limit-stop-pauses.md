# ai-usage-limit-pauses: a provider usage-limit stop is a pause, not a failure
depends-on: []

## Definition of done
1. When an implementor, reviewer, planner or researcher session ends with the provider's usage-limit message ('You've hit your weekly limit · resets <time>'), fac/review/implement read the reset time from it and record one factory-wide AI hold until that time (unreadable time: hold, and say so, never run on; lesson-3).
2. While the hold stands, no AI-role lease is taken; the merge queue and suites keep running.
3. The stopped run is given back without counting toward the item's attempts or the kill rule; no gap is parked or dead-lettered for it.
4. Nacks from a drain switch ('a switch drains the runs under way') are not counted as attempts either.
5. At the reset time the hold lifts by itself and the held items are taken again in their order.
6. SPEC/dev README say this in one paragraph.

## Acceptance tests
- tests/test_ai_limit_hold.py::test_a_weekly_limit_stop_holds_ai_leases_until_the_reset
- tests/test_ai_limit_hold.py::test_a_limit_stop_is_not_an_attempt_and_never_parks
- tests/test_ai_limit_hold.py::test_an_unreadable_reset_time_holds
- tests/test_ai_limit_hold.py::test_the_queue_runs_while_ai_is_held
- tests/test_ai_limit_hold.py::test_drain_nacks_are_not_attempts
- tests/test_ai_limit_hold.py::test_the_hold_lifts_at_the_reset

## Size budget
180 net lines

## Where it stopped

Built, round 1. Choices taken with nobody to ask (the most reversible each):

- The hold is a file, `run/ai_hold.json` (dev/bin/aihold.py), read by a sensor (`aihold.py held`) and the goal
  `ai-not-held` (on-stale off), which shuts implement-, review-, plan- and research-when; every AI program that holds a
  lease also gives its item back through `fac.drain_holds` while it stands. Deleting the file lifts it by hand.
- A limit stop is recognised only when a session's result *begins* with "You've hit your ... limit" (so a review that
  quotes the message is not a stop), or a failed session's own output holds it anywhere.
- An unreadable reset time (or an unreadable hold file) holds for one hour, said in the nack and on stderr; then the
  next session finds out again, and a probe that meets the limit again is itself uncounted.
- The run ends through `aihold.Limited` (a SystemExit with code 0, its uncounted nack printed first), so no
  `except Exception` (fac.guarded, the kill rule) can count it.
- "SPEC/dev README": the paragraph is in dev/README.md only; SPEC says nothing of the factory's drain or budget either.
- Item 4: drain nacks were already `count: false` (fac.drain_holds, drain.give_back); the test pins both, through
  ergostat's own lease fold.
- Not changed: plan.py's `except BaseException` still records the planner's whole reservation as its cost for a limit
  stop, as it does for any failure (an overstatement, never an attempt).
- Net lines outside tests/, docs/ and dev/: 0 (the code is all in dev/bin and dev/model).

Round 1, `ergostat check` findings sent back (auxiliary-without-causes auxiliary.ai-held, interface system.planning,
interface system.spending, missing-feedback goal.ai-not-held), each gone by a model change:

- `ai-held` is driven by `+stock.gaps-building, +stock.gaps-in-review` (the sessions run use the allowance up, as
  `ai-spend` is), so `ai-not-held`'s loop closes the long way (implement-when, implementor, gaps-started, gaps-building).
- `ai-held` and `ai-not-held` are in a system of their own, `ai-hold` (within oversight), so spending's interface is
  back to its 7 reads of `ai-budget`.
- Planning was at 10 information links with plan-when's new read: one expr block in planning, `ai-stopped`
  (`max(over, held)` of `goal.ai-budget.off` and `goal.ai-not-held.off`), now commands plan-when and plan-review-when,
  so the advisory plan review's AI session also waits out a hold (a small widening, said here; it already waited on
  the budget). The acceptance test pins this shape.
- `ergostat check` itself was refused to this session; the findings were read through `spec.read` and
  `architecture.findings` in a scratch test (removed, never committed): none of the four is left, and nothing new
  names planning, spending, ai-hold or the new parts.
