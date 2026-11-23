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

## Where it stopped

Built, round 1. 405 net lines outside tests, docs and dev (budget 600). Every done item has a test in
tests/test_runs_adopted.py (14 cases, all passing):
1 `test_a_killed_engine_s_run_is_taken_up_and_ends_normally_each_line_once` (engine SIGKILLed mid-run; lease renewed
as it is taken up, and the watchdog renews it instead of expiring it; ack, attempts 0),
2 `test_a_run_that_ended_while_no_engine_was_up_is_ended_at_the_time_it_ended` (its `agent.ran` and its series at its
keeper's exit time),
3 `test_an_engine_killed_while_taking_a_run_up_leaves_each_line_once[save|costs|lease|files]` (a crash after a batch's
events and before its offset, after the end and before its costs, before its lease's end, before its files go),
4 `test_a_pid_reused_by_another_process_is_not_taken_for_the_run`,
5 `test_a_run_whose_lease_was_taken_over_cannot_move_the_item`,
6 `test_two_restarts_during_one_run_lose_nothing` (the second engine a real `ergostat run`, so `start_all` takes it up).
Also: a run taken up is stopped by `block NAME --stop`; a run with no record is not taken for gone; `give_back` passes a
lease its keeper holds; line ids kept once in both event stores. Each was seen to fail with the code it guards broken
(line ids off, renew at take-up off, the watchdog's keeper check off, pid-only liveness, end time "now", a random
`agent.ran` id, the left-going lease finished in `_work`, registration in `procs` off, the pgid fallback off, the
sqlite and segments `line_id` uses off). The exception is the `give_back` filter: in a real stop only a race reaches
it, so its own unit test covers it.

Choices made with nobody to ask (each the more reversible one):
- "The offset commits atomically with the events it produced" is built as: the offset (`runs/RUN.offset`, with the
  counts, moves, nack and AI usage the lines came to) is written whole after the batch's events, and every event a
  journal line makes has an id from the run, the line's byte place and its count within the line (`store.line_id`, a
  context variable both event stores read when no id is given), so a line read again adds nothing. The effect asked
  (a crash between the two neither loses nor doubles a line) holds for every event; it needs no transaction across
  two files (segments, the default store, has none to join). Not undone on a re-read: an `auxiliary` set line's
  reading (one more sample of the same value); said in SPEC.
- The Files line names `ergostat/runner.py` and `ergostat/spec/watchdog.py`; neither changed. Block runs are in
  `spec/engine.py` (as the previous gap found), and the watchdog that expires leases is the dispatcher's
  (`leases/dispatch.py`), not `spec/watchdog.py`. The work is in a new `ergostat/spec/adopt.py`, with
  `spec/engine.py`, `spec/stream.py`, `store.py`, `segments.py` and `leases/dispatch.py`.
- The end time is the keeper's `exit` file's mtime (written as the run ends), so the exit file's format is unchanged.
- Only runs taken up are renewed on their keeper's word; a kept run in the engine that started it keeps today's
  activity-or-expire watchdog. A run taken up has no engine timeout of its own: its keeper's (timeout + 5 s) ends it,
  so no engine signals a pid that may have been reused. Its T1 spend cap is not applied after it was taken up, and
  its non-JSON stdout lines are not added to its run log (its stderr still is).
- A clean stop no longer gives back a kept run's lease (SPEC said it did, as the previous gap's known limit): the
  lease stays for the next engine, which is what "keep their leases" asks.
- The budget is left as it is: the next start's recovery closes the left run's reserve at the whole reserve, and the
  day is charged the larger of that and its real cost (never less than spent). Charging the real cost alone belongs
  to the budget.
- A run of a block no longer in the model, or with no `agent.started` in the record, is left as it is and said.

Not run here: the unit suite and the four browser files (the factory runs them). Run one file at a time:
test_runs_adopted.py, test_runs_outlive_engine.py, test_leases.py, test_lease_kill.py, test_compute_keeper.py,
test_upkeep_record.py, test_store_conformance.py (12 skipped: VictoriaMetrics, needs ERGOSTAT_TEST_VM_URL),
test_calls.py, test_runner_and_state.py, test_lease_end_turns.py, test_leased_workspaces.py,
test_lease_refused_cost.py, test_streamed_output.py, test_daemon_docs.py, test_segments_item_span.py: all pass. ruff
is clean. Local `main` has nothing the branch lacks, so no merge was needed.

### Round 2

532 net lines outside tests, docs and dev (budget 600). Each review finding, and what changed:
- settle() skipped what run_block does after a run's end. Now both share one routine, `Engine.after_end`: its failure
  triaged (`capture.failed`, or `capture.swallowed` for one that ended well, from its run log's tail and its input),
  `said.refused` said, its claims checked (`checks.check_all`), `outcomes()`, its `review`. `adopt.after` calls it for
  a run taken up. Its proposals are counted (`Said.tally`, shared too). A pooled workspace taken without a lease is
  released as run_block does (`leases.run_ended`). A kept run's record (`runs/RUN.json`) now carries what these need
  from its start: its run log's path (also put in its `agent.ran` as `log`), the item its context was given (for
  review), and its workspace. `RUN.offset` now saves `Said.claims` and `Said.proposals`. The steps after the end are
  marked done (`runs/RUN.settled`, removed with the run's other files), and run_block marks them too, so an engine
  killed after them (before its lease's end) does not do them again. An engine killed between them and the mark has
  them done again (a review asked twice) rather than not at all. Test:
  `test_a_run_ended_while_no_engine_was_up_has_what_follows_any_run_s_end[none|after|settled|lease]`: a claim made
  before the engine stopped is `verified` after the take-up, `review: [{by: none}]` gives one `review.skipped` of the
  run, and `agent.ran` has `log`; a crash at `after` still has them done, one at `settled` has them twice, and one at
  the lease's end once. It was seen to fail with claims not restored from the offset, with `after` not called, and
  with the `settled` mark ignored.
- Metrics a run wrote while no engine was up now keep their time. The keeper stamps the journal: every tick (0.25 s)
  in which it grew, `size time` is appended to `runs/RUN/stamps` (at most 100,000 stamps, about 7 hours of steady
  output; after that, lines are read at their reading). A run taken up gets each line's time from the first stamp
  covering it (`adopt.Stamps`, never later than now; NaN, non-numbers and stamps going back are passed over), and
  `Said` passes it as `at=` to the line's event lines, `valve.opened`, `auxiliary.set` and its reading, decisions,
  claims, proposals and refusals. A line not stamped yet is read at its reading, as in the engine that started the
  run. The bare number that settle takes is at the run's end time. Tests:
  `test_lines_printed_while_no_engine_was_up_keep_the_time_they_were_printed` (the event line and the valve opening
  printed 2 s before the take-up have their print time, within a second; a line read live has its reading's time),
  seen to fail with no stamps passed and with `valve.opened`'s `at=` off; `test_a_stamp_that_is_not_one_is_never_taken_for_a_time`.
  Only runs taken up use the stamps; the engine that started a run keeps its read time (the stamp comes up to a tick
  after the read, so a live run's lines would mostly have none). SPEC 9.1 now says this, in place of "stamped with
  the time they are read".

Known limits, said here and not built: a stopped engine's stamps are only as good as the keeper's tick. The end
steps are run under the model loaded now, not the one the run started under (the engine that started it is gone).
A claim's id is made from its time, so a claim line read again after a crash between its event and the offset, with
no stamp yet, gets a new id while its event is kept once (its check then finds a claim the record does not have).
`capture.failed` and the workspace release on a run taken up have no test of their own (the steps are run_block's,
whose tests cover them).

Not run here: the unit suite and the four browser files (the factory runs them). Run one file at a time, all pass:
test_runs_adopted.py (20), test_runs_outlive_engine.py, test_compute_keeper.py, test_claims.py, test_recipes.py,
test_runner_and_state.py, test_repair_traces.py, test_repair_log_events.py, test_leases.py, test_lease_kill.py,
test_leased_workspaces.py, test_streamed_output.py, test_store_conformance.py (12 skipped: VictoriaMetrics). ruff is
clean. Local `main` has nothing the branch lacks.

### Round 3

547 net lines outside tests, docs and dev (budget 600). The one finding, and what changed:
- `Adopted.poll()` read the run's start time (`runrecord.start_time`, a `ps` each call on macOS) on every poll,
  about 20 times a second for a quiet journal, for the run's whole life. Now `Adopted.alive()` reads it at most once
  every `adopt.CHECK` (1 s). Between readings it checks only that the pid is there (`os.kill(pid, 0)`), so a run
  that has gone is still seen at once. A pid once found to be another process's stays gone without being read
  again. Test: `test_a_run_taken_up_has_its_start_time_read_at_most_once_a_second`. It polls every 0.05 s for 3 s
  and allows 3 to 5 readings. It checks that a reused pid is not read again and stays gone, and that a killed pid
  is seen before the next reading. It failed with poll calling `alive(rec)` directly (60 readings), and with the
  "stays gone" rule removed. SPEC 9.1 says this.

Not run here: the unit suite and the four browser files (the factory runs them). Run one file at a time, all pass:
test_runs_adopted.py (21), test_runs_outlive_engine.py (11). ruff is clean. Local `main` has nothing the branch lacks.

### Round 4

The one finding was a conflict with main in `ergostat/compute/worker/keeper.py`. It came from main's `wait4` and
`reaped` CPU file meeting the branch's journal stamps. Main 28ad5c4ad880 is merged, and both changes are kept: each
tick the keeper stamps the journal, then reaps the run with `os.wait4` and writes `reaped`. The docstring now says
both. No other code changed.

Not run here: the unit suite and the four browser files (the factory runs them). Run one file at a time after the
merge, all pass: test_compute_keeper.py (5), test_runs_adopted.py (21), test_runs_outlive_engine.py (11),
test_compute_readings.py (6), test_compute_connection.py (10). ruff is clean.
