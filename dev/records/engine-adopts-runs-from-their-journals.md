# engine-adopts-runs-from-their-journals: a starting engine takes up the runs still going and consumes what they wrote while it was down

depends-on: [runs-keep-going-without-the-engine]

Problem. Once runs outlive the engine, a new engine must pick them up: consume each journal into the event log exactly once, keep their leases, and settle the ones that finished while it was down.

Change.
- On start, the engine lists run folders, and for each one with a live keeper or an unconsumed journal takes it up from its saved offset. The offset commits atomically with the events it produced, so a crash between the two neither loses nor doubles a line.
- A lease held by a run still alive is kept with its fence: the watchdog does not expire it while the keeper reports the run alive (pid and start time, so a reused pid does not count), and time the engine was down does not count against it. A run's timeout still does.
- A run that finished while the engine was down is ended from its journal and exit as if the engine had been there: `agent.ran`, its ack or nack, its cost.
- A journal line whose fence is stale is recorded as refused, as a late line is today.
- Metrics a run wrote while the engine was down keep their original timestamps.

Definition of done.
1. Kill the engine mid-run, restart it: every line is in the event log exactly once and the run ends normally, with no attempt counted.
2. A run that finishes during the outage is settled on the next start, with the time it really ended.
3. Kill the engine during adoption, at each step: still exactly once.
4. A pid reused by another process is not taken for the run.
5. A run whose lease was taken over (a newer fence) cannot move the item.
6. Two restarts in a row during one run lose nothing.

Files: ergostat/runner.py, ergostat/leases/dispatch.py, ergostat/spec/watchdog.py, tests/test_runs_adopted.py (new), docs/SPEC.md.
