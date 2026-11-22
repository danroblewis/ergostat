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
