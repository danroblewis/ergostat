# manager-reads-the-queue-holder: when merges stop, the pipeline manager names what holds the merge queue before it proposes a cause

depends-on: []

Three times on 2026-11-22 (06:25, 07:24 and 08:15) the pipeline manager asked the coordinator to lower the implementor pool because "the interlock holds the queue shut". Each time suites-running was below its limit and the interlock was open. The queue's one slot was held by a finished run's lease (`gap/ui-agents-a-group-heading-counts-its-rows`, merged at 05:45), which the watchdog kept renewing. The manager's brief has no line that says who holds the merge queue's lease, how long since it was renewed, whether its run's process is still alive, or what the queue-when inputs read.

## Definition of done
1. The manager's brief (built in dev/bin, beside its other evidence) includes, whenever approved gaps wait and nothing merged for 20 minutes: each lease held by the merge-queue block (item, run id, taken, last renewed, expires, the item's state), whether that run's process is alive, and the live readings of queue-when's inputs (approved-gaps-landed, machine-quiet, suite-threads-within, suite-memory-within, push-waiting).
2. dev/prompts/ (the pipeline manager's prompt) says: when merges stop, name what holds the queue from that evidence before proposing a cause; a held lease on an item already merged is a stuck lease, not starvation.
3. A unit test builds the brief for a record with a merged item still leased by merge-queue and checks the lines are there.

## Files to touch
The manager's brief builder in dev/bin, its prompt in dev/prompts, a test.

## Size budget
50 net lines of code outside `tests/` and `docs/`.
