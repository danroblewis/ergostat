# queue-keeps-a-suite-slot: the merge queue is never starved by implementor suites
depends-on: []

When many gaps are building, their suites fill the machine's suite slots (goal.machine-quiet, suites-running <= 6). Then the queue-when valve stays off and no merge happens while approved gaps wait. This happened on 11-20 (intervention/interlock-starved-queue) and again on 11-22 14:16, with 17 approved and about 35 building.

## Definition of done
- While goal.approved-gaps-landed is off and no queue run holds a slot, an implementor or triage session waiting for a machine-wide suite slot ([suites] slot) does not take the last free slot. One slot is kept for the merge queue.
- queue-when counts the kept slot as free for the queue. Implementor suites alone never hold the queue off on machine-quiet. Threads and memory still hold it.
- A queue held off by the interlock for longer than [manager] broken_minutes says which reading holds it (suites-running, threads, memory or push-waiting) in the broken situation's text.
- SPEC and dev/README describe the kept slot.

## Acceptance tests
- tests/test_suite_slots.py::test_the_last_slot_is_kept_for_the_queue_while_approved_gaps_wait
- tests/test_suite_slots.py::test_the_slot_is_free_to_implementors_when_nothing_is_approved
- tests/test_manager.py::test_a_broken_situation_names_the_interlock_reading_that_holds_the_queue

## Size budget
120 net lines outside tests and docs.

## Where it stopped

Built, round 1. 120 net lines outside tests and docs (dev/ counted: slots.py 84, fac.py 18, watch.py 15, factory.toml
2, interlock.yaml 1); 0 of core code as fac.net_lines counts it (dev/ is left out there).

- `dev/bin/slots.py`, `gate()`: fac.suite runs each suite in `[suites] slot` inside it (the implementor's, triage's,
  and so also the manager's reapprove rerun and measure runs). It waits while approved gaps wait, no queue run holds
  its slot, and the suites ps sees plus the factory's own that passed in the last 60 s reach `[suites] slots - 1`. The
  look and the take are under `run/slots.lock`; the acceptance test runs two at once and only one passes.
- Choices made with no one to ask, each the reversible one: `[suites] slots` is a new setting (default 6, 1 to 32,
  checked in fac.config and again at run time) rather than read from the slot command, which ergostat cannot see. "A
  queue run holds its slot" is read as run/queue.json's `running` with the queue's lock held (a `running` left by a
  dead run, the lock free, does not count). An unreadable record counts as approved gaps waiting (the slot kept).
- The queue's own in-run wait (`fac.wait_quiet` in queue.py) waited for fewer than `[load] most_suites` (4) suites, so
  five implementor suites would still have held a queue run that queue-when had started. It now waits for fewer than
  `[suites] slots`: the kept slot free is free for it. This is the one change beyond the four done items' wording, made
  because without it the title is not true.
- machine-quiet's hold (`<= 6`) is unchanged: with the kept slot, implementor suites alone are at most 5, inside it.
  tests/test_suite_slots.py checks the model's hold against the default.
- The broken `interlock` condition's text names each reading over its limit with value and limit (`suites-running 8
  over 6`, `threads`, `memory`) and `push-waiting 1` from the sensor's own command (`queue.py waiting`), "unreadable"
  when it cannot be read.
- Not covered: suites that someone else starts outside the factory still take the kept slot; dev/README says so.

## Where it stopped

Parked by the factory (dead-letters, 2026-11-23 09:13).

Its runs failed past their attempts (a dead letter):
- attempt 8: nack queue: the push of 166e5ae0fd95 (gap/graph-draws-every-dependency) is requested
- attempt 9: nack queue: the push of 76e1a9ab1945 (gap/perf-segments-item-span-first) is requested
- attempt 10: nack queue: the push of 2985c7826921 (gap/milestone-kind-and-lifecycle) is requested
- attempt 11: nack the implementor pool is full (run/pools.json): waits its turn
