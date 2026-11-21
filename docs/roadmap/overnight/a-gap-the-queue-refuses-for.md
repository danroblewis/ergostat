# queue-refused-reaches-fix: a gap the merge queue sends back for conflicts with main ends in fix, not approved

depends-on: []

## Definition of done
- When the queue's refuse() (dev/bin/queue.py) sends back the run's own gap (the one it holds the lease on), the gap ends in fix with sent_back_by: queue and its conflict findings. The lease ending afterwards must not nack it back to approved.
- The same holds for a send-back held by tell() until the push settles: the gap still reaches fix once the run ends.
- The landing model's sent-back-by-queue flow (dev/model/landing.yaml) counts these send-backs.

## Acceptance tests
- tests/test_queue.py::test_a_conflicting_own_gap_ends_in_fix_not_approved: a queue run whose only gap conflicts with main leaves it in fix with the conflict finding. Fails today: it ends approved.
- tests/test_queue.py::test_a_held_send_back_reaches_fix_after_the_run: the held-outcome path ends in fix too.

## Size budget
40 net lines
