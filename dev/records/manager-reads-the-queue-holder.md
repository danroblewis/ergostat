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

## Where it stopped

Built, round 1. `queue_holder()` in `dev/bin/manager.py` adds *What holds the merge queue* and *queue-when's inputs,
read now* to the brief whenever approved gaps wait and nothing has merged for 20 minutes. That window is `QUIET`, fixed
at the definition's 20 rather than tied to `[manager] broken_minutes`, so scheduled sessions get the section too.
`run_alive()` reads the engine's run record (`runs/RUN.json` in the state dir) and compares the pid's start time. A
record or start time it cannot read is reported as unknown, never as gone. A missing record is reported as missing,
since the engine removes the record when a run ends. machine-quiet, suite-threads-within and suite-memory-within are
read with `load.reading` against their holds in dev/model/interlock.yaml. push-waiting is read by running its own sensor
command (`queue.py waiting`) in a subprocess, because importing dev/bin/queue.py would shadow the standard library's
`queue`. The prompt's new *Merges stopped* pattern tells the manager to name the holder from that evidence first, and
says that a lease held on a merged item is a stuck lease, not starvation. dev/README's pipeline-manager section says
what the brief now carries. Acceptance test:
`tests/test_factory_manager.py::test_when_merges_stop_the_brief_names_what_holds_the_merge_queue`. I broke the liveness
comparison, and separately the merge-queue block filter, and saw the test fail both times.

Overrun reason: about 64 net lines in dev/bin/manager.py plus 5 in the prompt, against 50. dev/bin uses only the standard library and never imports ergostat, so the liveness check cannot import ergostat/spec/runrecord.py and has to repeat its Linux and macOS start-time reads (about 20 lines). Each of queue-when's five inputs also has its own read, so that an unreadable reading is reported as unreadable, never as within its limit.
