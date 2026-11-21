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

## Where it stopped

Round 1, by the implementor. The two acceptance tests are written and pass. No code changed: 0 net lines.

**The premise did not reproduce.** "Fails today: it ends approved" does not hold on this branch's main (94c5255b).
The tests do more than the fixture's fold, which plays no lease. They load the factory's own model (ergostat.yaml
and dev/model) into a real ergostat project. They record queue.py's actual output under a merge-queue lease and end
that lease through the engine's own `Dispatcher.finish`. Run that way, a conflicting own gap is already acked into
`fix` with `sent_back_by: queue` and `conflicts with main: app.py`, because merge-queue's `takes.to` holds `fix`.
The held path ends in `fix` too, once `queue.py settle` releases it. The flow `sent-back-by-queue` (its own sensor,
read by `items.measure`) counts both. I found nothing to change for the three points of done. Building a change
anyway would go against the owner's rule to build only what was asked, so I chose the more reversible option: tests
only.

**The tests can fail** (each break made by hand, the test watched fail, then put back):
- `fix` removed from merge-queue's `takes.to` (dev/model/landing.yaml): the first test fails, the gap ends
  `approved`. That is the symptom this definition describes, so the tests reach it.
- `release({"then": HELD["said"]})` in `main()`'s finally emptied: the first test fails (no gap.sent-back said).
- `release(p)` in `settle()`'s `ran` branch emptied: the second test fails (stays `push-pending`).

**Found, and not fixed here** (outside this definition: it asks for `fix`): when the conflict is the gap's last gate
by the kill rule, refuse() parks it (`review.park`, `gap.parked`). `parked` is not in merge-queue's
`takes.to: [merged, fix, queue-failed, push-pending]`. So the lease end nacks the parked gap back to `approved`. I
checked this the same way (failed_gates 2 of kill_after 3: it said `gap.queued, gap.measured, gap.parked`, then
ended `approved`). That may be the report behind this gap. Its fix is likely `parked` added to `takes.to`, with a
test like these. It belongs in a gap of its own.

**Not run here:** the unit suite as a whole and the four browser files (the factory runs them after this). This clone
has no `origin` remote, so origin/main could not be merged. Local main is an ancestor of HEAD.
