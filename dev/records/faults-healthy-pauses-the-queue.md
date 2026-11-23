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

## Where it stopped

Built, round 1. All five done items have tests in `tests/test_faults_healthy.py`, and the tests pass.

- Done 1: `test_an_unhealthy_queue_starts_nothing_and_starts_again_when_it_recovers`, and
  `test_an_unreadable_healthy_holds_the_queue_and_says_unknown`, `test_unknown_is_never_healthy` and
  `test_a_hold_an_earlier_engine_left_open_is_ended_once`.
- Done 2: `test_a_run_failing_during_the_outage_spends_no_attempt[False|True]` (failing while down, and failing after
  it went down and came back during the run), and `test_a_run_silent_through_the_outage_expires_uncounted`.
- Done 3 and 4: `test_a_run_failing_while_healthy_counts_as_today[faults|no faults]`,
  `test_a_model_with_no_faults_reads_nothing_for_health`.
- Done 5: `test_check_refuses_a_healthy_naming_a_part_that_does_not_exist[...]`, `test_ergostat_check_refuses_it`.

Choices nobody was there to answer. I took the most reversible option each time:

- **Where the code is.** The `takes` schema is in `ergostat/leases/compile.py` (the key, plus one call) and
  `ergostat/spec/ir.py` (`Takes.healthy`), not in `ergostat/spec/`. Reading `healthy`, checking it and the hold events
  are a new module, `ergostat/leases/faults.py`, which keeps `dispatch.py`'s change small.
- **"A sensor, goal or command".** `sensor.NAME` is no reference kind in ergostat, so `healthy: sensor.NAME` resolves at
  `check` to the stock, flow or auxiliary NAME that a sensor reads. `stock.`, `flow.` and `auxiliary.NAME` are taken
  as written, and all of these are healthy above 0. `goal.NAME` is healthy while the goal holds (`.off` is 0).
  "Command" is taken in ergostat's own sense: a block's output, `block.NAME[.PORT]`, healthy above 0. A shell command
  run at dispatch is not built (it would run a process at every look).
- **Unknown**: no reading, not a number, a stale reading (`observer.stale_age`), a goal not worked out yet or whose part
  is stale, or an exception while reading. Each holds the queue. For 30 s after the engine starts or wakes
  (`faults.QUIET`), an unknown holds without recording a hold. Without that, every engine start recorded a hold of
  about a second before the sensor's first reading.
- **Events**: `ergostat.queue.held` and `ergostat.queue.resumed`, about the block (as `ergostat.run.killed` is). The
  resume is caused by the hold and carries `since`, `until` and `held`. An engine that starts takes up a hold the last
  one left open. A block whose `faults:` is removed while it holds has its hold ended.
- **"Became unhealthy during the run"** is counted by sequence, not by time (lesson 2): each look that finds it
  unhealthy adds to a per-block count. A run whose count moved between its take and its end went through an outage.
  Looks are once a second, so an outage shorter than that can be missed (said in SPEC).
- **Expiry**: a counted expiry through an outage is uncounted the same way. The definition only says "a run that
  fails", and a silent expiry is one way a run fails.
- **The cause on the item**: the nack's `why` ends `(not counted: CAUSE)`, which the lease history keeps. The end
  event carries `fault`. The fold is unchanged.
- **Not done**: "why isn't this done?" and the charts are not wired to the new events. The definition asks only that
  they can read them, and no new page was wanted. `ergostat block NAME --now` still runs whatever `healthy` reads,
  but a failure through an outage is still uncounted.

Net code is about 200 lines, within the 600 budget. Tests run: `tests/test_faults_healthy.py` (23 passed), plus
`tests/test_pool_now.py`, `tests/test_leases.py`, `tests/test_lease_end_turns.py`, `tests/test_lease_kill.py`,
`tests/test_take_order.py` and `tests/test_library_trust.py::test_every_compile_key_classified`, all passing. Each new
dispatch, check and read path was broken by hand, one at a time, and its tests failed. I did not run the whole unit
suite or the browser files: the factory runs them. No page changed.
