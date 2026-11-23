# faults-healthy-pauses-the-queue: a queue whose shared environment is down waits, and blames no item

Owner, 2026-11-23, on a merge queue stuck for hours: the general problem is head-of-line blocking, and the response depends on the kind of fault. This is level 1 of the fault-isolating queue: a fault in the shared environment.

Change. `takes` gains an optional `faults:` with `healthy:`, a sensor, goal or command:

```yaml
takes:
  kind: todo
  at: ready
  faults: {healthy: sensor.jira-reachable}
```

- While it reads unhealthy, the block takes no new item from this queue.
- A run that fails while it is unhealthy, or that became unhealthy during the run, is given back uncounted, with the cause recorded on the item.
- It resumes by itself when healthy again.
- An unreadable `healthy` is unknown: it holds the queue and says so. It never counts as healthy.
- The hold is an event with its cause and start and end time, so charts and "why isn't this done?" can read it. No new page.

Definition of done.
1. A queue with an unhealthy sensor starts nothing, and starts again when it recovers.
2. A run failing during the outage spends no attempt and parks nothing.
3. A run failing while healthy is treated exactly as today.
4. A model with no `faults:` behaves exactly as today.
5. `ergostat check` refuses a `healthy:` naming a part that does not exist.

Files: ergostat/spec (the `takes` schema), ergostat/leases/dispatch.py, tests/test_faults_healthy.py (new), docs/SPEC.md section 9.5.
