# shard-moved-flow-read-by-owner: after a run moves a flow, each of the flow's stocks is read at once by the one engine whose shard owns it
depends-on: []

## Definition of done
- With `shard=None` nothing changes: after a run moves a flow, the sensors of both of its stocks are read at once, and their reading's cause is that run.
- A shard engine reads at once only the sensors of a moved flow's stocks that are in its own shard (`Plan.of`). It never reads another shard's sensor.
- The engine that owns a stock reads its measured sensors at once when the record shows a run that moved a flow into or out of that stock. Today the run's ended event carries `data.moved`, and this engine follows that event the way it follows the owner's asks: by `seq`, under the model it read for the event. It reads each sensor once, and the reading's cause is the run named in the event. When the moving run is in its own shard, the reading after acting already does this, and the stock is not read a second time.
- No read is made for a flow or stock the follower's model does not have, a flow moved by 0, or an event without `moved`.
- SPEC §9.8's "Not yet by shard" no longer says a moving flow's sensors are read wherever they are, and the shard text says who reads them. The GAPS entry's "Left" drops this item.

## Relation to other work
- gap/shard-wires: carries in-memory values between shards. A stock with a sensor is never a wire, so this change does not overlap it. It does not touch `spec/shards.py`.
- gap/shard-supervisor: shards in separate processes learn about the run through the record, the same way they learn about the owner's asks, so nothing here needs it.
- shard-daemons-file-each: a sibling sub-gap. Each one removes only its own item from SPEC §9.8 and GAPS.

## Files to touch
- `ergostat/spec/engine.py`
- `tests/test_engine_shard.py`
- `docs/SPEC.md`
- `docs/GAPS.md`

## Risks
- lesson-2: the follower decides which runs it has already seen by comparing times, so it reads one event twice or misses one. It must follow by `seq`. `test_moved_flow_read_once_each` guards this.
- lesson-3: a moved flow whose stock is in no shard of the follower's model, or an event with no `moved`, is read as "read everything" or raises out of the follow loop. `test_moved_flow_unknown_reads_nothing` guards this.
- lesson-9: the test passes even with no follower, because the moving shard still reads the other stock itself. The test asserts which engine took each reading, and is seen to fail with today's `after_acting`.

## Acceptance tests
- `tests/test_engine_shard.py::test_moved_flow_read_by_owner`: the flow goes from a stock in shard `a` to a stock in `b`, and `a`'s block moves it. `a` reads its own stock at once and never reads `b`'s. `b` reads its stock at once, with the cause set to `a`'s run. This test fails on main.
- `tests/test_engine_shard.py::test_moved_flow_read_once_each`: when the record is followed twice (before and after a newer event), each stock gets one reading from the run. A stock in the moving run's own shard gets one reading, not two.
- `tests/test_engine_shard.py::test_moved_flow_unknown_reads_nothing`: an ended event whose `moved` names a flow the model does not have, or a flow moved by 0, causes no reading, and the follow loop keeps answering the owner's asks.

## Size budget
50 net lines
size: S (confidence: low)

## Notes from the plan review (answer each)

- ergostat/spec/engine.py:1172 writes the ended event as `agent.failed` or `agent.ran`, and a failed run still carries `data.moved` (run_block returns said.moved either way, :1205). The follower must query both types in _follow (:1710-1714). Otherwise a failed run that moved a flow leaves the other shard's stock unread, while the moving shard used to read it.
- The reading's cause in the follower is the event's `causedby` (the begun id, the same value `last_run` holds, :988), set in read_cause under self.lock as `_run` does (:838-842). Use `e['causedby']`, not the ended event's own id.
- 'Not read a second time' needs one rule, written down in one place. after_acting (:851-857) filters each sensor by self.own(f"{s.of.kind}.{s.of.name}.{s.name}") (the key at :1575). The follower skips events for a block it `follows` itself (its own runs are already read by after_acting) and reads only the sensors it owns. With shard=None the follower must make no read at all. Watch a swap that moves the block between the run and the follow: then neither engine or both may read it. Name which one happens in a comment or a test.
- Both the event's `moved` and its values come from the record: a non-dict `moved`, a non-number or NaN amount, or a flow or stock the model lacks must each be skipped inside the loop, never raised. An exception in _ask's caller (:1718-1720) would skip the `seq` advance for the rest of that batch. Treat negative amounts on two-way flows as moved (only 0 is skipped, as `if v` does at :1205).
- shard-daemons-file-each (ready) edits the same SPEC §9.8 'Not yet by shard' paragraph (docs/SPEC.md:3394-3397), the same GAPS 'Left' clause and tests/test_engine_shard.py. After merging main, reread that paragraph and that GAPS entry as whole sentences, for splices and a duplicated Left clause.
- test_moved_flow_read_by_owner must fail with today's after_acting: assert that shard a's engine made no read of b's sensor (e.g. record read_soon calls per engine). A check that b's series got a reading is not enough. In test_moved_flow_read_once_each, call the follower step twice across a newer event and count the reads per series.

## Where it stopped

Built, round 1. Net code lines: +52 -24 (28 net) in `ergostat/`, within the 50 budget.

- `Engine._read_moved(flows, cause, spec)` is the one rule: the sensors `after_acting` names, kept only where
  `own(sensor key)` (all with `shard=None`; a key in no shard of the plan: not read), each with its cause and
  `read_soon`. `_run`, the leased-item run (`leases/dispatch.py`) and the step test (`control/steptest.py`) all use it,
  so no shard engine reads another shard's sensor after acting. `after_acting` itself is unchanged (it also feeds the
  pacing and `fresh_for`, which keep reading across shards); it only takes an optional `spec`.
- `Engine._moved(e)` follows a run's ended event: nothing with `shard=None`, nothing for a block the engine `follows`
  (its own runs, read in `_run`), else `_read_moved` of the flows with a non-zero int/float amount (NaN, bool, strings
  skipped; negatives read), cause `e["causedby"]` (the begun id), under the one `self.spec` read for the event.
- `_follow`'s look is now `_follow_once(seq) -> seq` (so a test can step it); a shard engine also queries
  `agent.ran,agent.failed`. Each event is handled inside a try: one event's fault is said and the rest of the batch,
  and the `seq` advance, go on (an `_ask` that raised used to end the follow thread; now it is said instead).

Answers to the plan review's notes:
- Failed runs: both `agent.ran` and `agent.failed` are queried (`test_moved_flow_read_once_each` uses a failed one;
  seen to fail with `agent.ran` alone).
- Cause: `e["causedby"]`, set under `self.lock` in `_read_moved`, as `_run` did.
- One rule: `_read_moved`, above. Swap between run and follow (the most reversible choice, no new field in the
  record): the new owner follows the block now and skips the run, so its stocks are read at their schedule, by neither
  engine at once, never twice. Said in `_moved`'s docstring and SPEC §9.8; no test pins it.
- Malformed record values are skipped in `_moved`, never raised (`test_moved_flow_unknown_reads_nothing`: unknown flow,
  0, "3", True, NaN, a list, a string, no `moved`, `data` None; then a stop ask is still answered).
- shard-daemons-file-each: not on `main` in this clone (main has no new commits past the base), so no merge was needed;
  the 'Not yet by shard' paragraph and the GAPS entry were reread as whole sentences after the edit.
- Lesson-9, seen to fail: the `own` filter removed in `_read_moved` (today's `after_acting` behaviour) fails
  `test_moved_flow_read_by_owner` and `test_moved_flow_read_once_each`; the `follows` skip removed fails both
  (a's stock read twice); the NaN check removed fails `test_moved_flow_unknown_reads_nothing`; `agent.failed` not
  queried fails `test_moved_flow_read_once_each`.

Files beyond the definition's list: `ergostat/leases/dispatch.py` and `ergostat/control/steptest.py` (one line each:
they read after acting too, and would otherwise read another shard's sensor), and the fake engines in
`tests/test_control.py` and `tests/test_rga.py` (they stubbed `after_acting`; now `_read_moved`).
