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
