# daemons-reconnect-after-the-engine: a daemon keeps running through an engine restart and picks its messages back up

depends-on: [engine-adopts-runs-from-their-journals]

Owner, 2026-11-23: "for daemons, the ones that receive messages from ergostat, that may be different, but even those could be separated."

Problem. A daemon (SPEC 9.7) is a child of the engine and receives its messages over a connection to it, so it stops with the engine.

Change.
- A daemon runs under a keeper as runs do, with its output in a journal.
- Messages to it are delivered from a durable position: while no engine is up it simply receives nothing and keeps doing what it holds. A new engine reconnects and delivers from where it left off, at least once, with an id the daemon can use to drop a repeat.
- A daemon declared to stop with the engine keeps that behaviour.

Definition of done.
1. Kill the engine with a daemon mid-item: the daemon finishes the item, and its result is recorded after restart.
2. A message sent before the kill and not acknowledged is delivered again with the same id; none is lost.
3. A daemon that died during the outage is restarted by the new engine.
4. Existing daemon tests pass.

Files: ergostat's daemon modules, tests/test_daemons_outlive_engine.py (new), docs/SPEC.md.

## Where it stopped

Built, round 1. Every definition-of-done item has a passing test in `tests/test_daemons_outlive_engine.py`:
1. `test_a_daemon_finishes_its_item_through_an_engine_kill_and_its_result_is_recorded_after` (engine group SIGKILLed
   mid-item, the daemon finishes with no engine up, the next records one `agent.ran`, the item moved, the lease acked;
   the saved offset rewound to 0 to show a line read again adds no event).
2. `test_a_message_not_answered_is_sent_again_with_its_id_and_none_is_lost` (sent again with the same `run` id to the
   same process; the lease renewed as taken up and by the watchdog, `seen: keeper`; the answer recorded once), and
   `test_a_run_is_in_its_daemon_s_state_before_its_line_is_sent`.
3. `test_a_daemon_that_died_while_no_engine_was_up_is_restarted_and_given_what_it_held`.
4. Run on this branch, one file at a time, all passing: test_daemons, test_daemons_restart, test_daemon_lines,
   test_daemon_observations, test_daemon_yaml_review, test_ticket_factory_daemons, test_daemon_docs, test_warm,
   test_engine_shard, test_engine_shard_asks, test_resilience, test_agents, test_runlog, test_runs_adopted,
   test_runs_outlive_engine. Not run here: the whole unit suite and the browser files (the factory's and the queue's).
Also: a changed command drained (`test_a_daemon_whose_command_changed_...`), a clean stop leaving it going,
`run --stop --runs` stopping it, input lag counted against `stdin-timeout`, and the declarations below.
Each of done 1-3's mechanisms was broken by hand and seen to fail its test (event ids per line, the resend, the
hand-over of a dead process's runs, the state written before the line is sent: the last needed the new unit test).

Decision taken with nobody to ask (the most reversible): kept is opt-in, `outlive-engine: true` on a daemon, by
default what `runs: outlive_engine` says (as runs do), never a warm daemon; with neither, nothing changes.

Left, said in SPEC §9.7: a kept process's inbox and journal grow for its life (no rotation); a reading asked and not
answered before the engine stopped is not sent again; a kept daemon's journal is taken line by line (not in batches of
500), so its event ids are per line; the restart-in-place path (the watchdog's exec) is untested for kept daemons;
nothing was run on macOS (the start time a kept process is known by comes from `ps` there).

Round 2, the review's two findings (both blocking; there were no others):
1. A kept daemon no longer kept (removed, renamed, `outlive-engine: false`, `runs: outlive_engine` dropped) was never
   looked at again. Now `kept.sweep`, on the engine's first sync, looks in every `<state>/daemons/KEY/`, takes up each
   process no kept slot claims (its runs of a block still using that daemon held and recorded), and drains it (still
   going) or lets it go (ended, its runs given back uncounted); another shard's daemon is left to it, one the plan
   does not name to the lead. The supervisor's loop now also runs while only processes draining are left. Tests:
   `test_a_daemon_no_longer_kept_is_taken_up_drained_and_its_run_recorded`, `test_a_daemon_removed_from_the_model_is_stopped`.
   SPEC §9.7 says what holds, including that a run whose block no longer uses the daemon is not taken up (its lease
   expires as any other's) and the process is stopped within the grace.
2. Runs left held by no process. The dead process's runs now move into the new process's state before the old
   state is removed; if the launch fails they end `agent.failed` and their items are given back uncounted
   (`test_a_run_whose_daemon_cannot_be_started_again_is_given_back`, with `keeper.launch` made to raise). The stale
   path in `_spawn` now drains the process instead of killing it with its taken-up runs in it
   (`test_a_daemon_taken_up_but_no_longer_wanted_finishes_what_it_holds`). `_through` now ends a run its holder no
   longer has at two looks in a row (`kept.unheld`; the holder changes under the holder's lock with the run in its
   runs, `test_a_run_taken_up_that_no_process_holds_is_ended`).
Each fix was broken by hand and seen to fail its test: the sweep call removed (both sweep tests fail), the hand-back
on a failed launch removed (fails), the old stop-and-kill stale path restored (fails). Run again one file at a time,
all passing: test_daemons_outlive_engine (15), test_daemons, test_daemons_restart, test_warm, test_daemon_lines,
test_daemon_observations, test_resilience, test_engine_shard, test_ticket_factory_daemons, test_runs_outlive_engine,
test_engine_shard_asks, test_daemon_docs, test_runs_adopted, test_daemon_yaml_review, test_agents, test_runlog; ruff
clean. Not run here: the whole unit suite and the browser files. No sweep test runs with shards.
Overrun reason: 618 net lines against 600: the 18 over are round 2's two blocking fixes (the sweep of daemons no longer kept, and runs handed back when a restart's launch fails or its holder lets them go); nothing else was added.

## Entry

section: Runtime, scale and latency

- **A daemon outlives its engine** (done, on `daemons-reconnect-after-the-engine`; SPEC §9.7): `outlive-engine: true`
  (default `runs: outlive_engine`; never warm) runs a daemon under a keeper through a relay that feeds its input from
  an inbox file, its output a journal read from a saved offset. Stopped or killed, the engine leaves it going; the
  next takes up the runs it held (saved before each hand-over), reads the journal to its end, sends again what is
  unanswered with the same `run` id (at least once), restarts one found ended with its runs (given back, uncounted,
  if the restart fails), drains one whose command changed, and drains or lets go a process of a daemon no longer
  kept. Not done: inbox and journal rotation, readings sent again, the restart-in-place path tested.
