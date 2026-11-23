# runs-keep-going-without-the-engine: a run is not killed when ergostat stops, and writes its lines to its own journal

Owner, 2026-11-23: "when our ergostat server dies, we want the in-progress jobs to work just fine, their only responsibility is to produce the jsonl that ergostat will later consume into its event log, and maybe metrics. there is no reason those should need to have a hard dependency on ergostat."

Problem. A run's stdout is a pipe to the engine (ergostat/runner.py), and the engine kills each run's process group as it stops (SPEC 9.5). So every restart, crash or version switch ends all running agents, and their uncommitted work and tokens are lost. Switches drain for this reason.

Change.
- A block's run starts under a detached keeper in its own session (reuse ergostat/compute/worker/keeper.py rather than writing a second one). The keeper owns the run's process, records its exit, and needs no engine to exist.
- The run's stdout goes to an append-only JSONL journal in the run's folder (`runs/<id>.jsonl`), flushed line by line. The format is the existing run line protocol (SPEC 9.1). The engine reads the journal; it is no longer the other end of a pipe.
- Stopping ergostat, on purpose or by a crash, leaves runs going. `ergostat run --stop --runs` (or a block's `--stop`, a lease expiring, a timeout) is what stops a run. Those keep working through the keeper.
- A call a run makes to the engine (SPEC 9.1, `ERGOSTAT_SOCKET`) while none is up must not fail the run: what only records is written to the journal; what needs an answer waits, as it does now, for longer than an engine restart takes.

This gap does not read journals back after a restart: that is `engine-adopts-runs-from-their-journals`. Until that lands, keep today's behaviour behind one setting, `[runs] outlive_engine` (default false).

Definition of done.
1. With the setting on, a test starts a run, SIGKILLs the engine, and the run carries on to its end, its journal complete and its exit recorded.
2. The same with a clean `ergostat run --stop`.
3. A run's lines in the journal are byte-for-byte what it printed, in order, including a last line with no newline.
4. An explicit stop of a run, a lease expiry and a timeout each still end the whole process group.
5. With the setting off, every existing runner test passes unchanged.

Files: ergostat/runner.py, ergostat/compute/worker/keeper.py, ergostat/spec/runrecord.py, tests/test_runs_outlive_engine.py (new), docs/SPEC.md.

## Where it stopped

Built, round 1. All five items have tests in tests/test_runs_outlive_engine.py (10 tests, all passing):
1 `test_a_run_carries_on_to_its_end_when_its_engine_is_killed` (SIGKILL to the engine's whole process group),
2 `test_a_run_carries_on_to_its_end_when_its_engine_is_stopped`, 3 the journal bytes are checked in both of those and
in `test_the_journal_is_what_the_run_printed_and_the_engine_takes_it_from_there`, 4
`test_each_way_of_stopping_a_run_ends_its_whole_process_group[stop|lease|timeout]` and
`test_run_stop_runs_stops_what_was_left_going`, 5 the existing tests/test_streamed_output.py, test_runner_and_state.py,
test_compute_keeper.py, test_calls.py and test_lease_kill.py pass unchanged, plus
`test_with_the_setting_off_the_engine_stops_its_runs_as_before`.

Choices made with nobody to ask (each the more reversible one):
- The setting is the top-level YAML key `runs: {outlive_engine: true}` (the definition's `[runs] outlive_engine`),
  main file only or `ergostat.local.yaml` (it is about the machine the engine runs on), and in the JSON schema. The
  key keeps the definition's underscore rather than the model's usual dashes.
- The files touched are wider than the Files line: block runs are started by `ergostat/spec/engine.py` (with
  `spec/stream.py`), not by `ergostat/runner.py`, which is the old TOML runner and is unchanged. The setting needed
  `spec/load.py`, `spec/compile.py`, `spec/ir.py` and the schema; the calls needed `cli/fast.py`; `--runs` needed
  `cli/running.py` and `cli/__init__.py`.
- The journal is the run's own stdout descriptor, opened O_APPEND by the keeper before the command (no process in
  between that could buffer or die), at `<state>/runs/RUN.jsonl` beside the run's other files. The keeper's folder
  is `<state>/runs/RUN/`. A run the engine read to its end has its journal removed, as `RUN.out` was.
- A run left going records no `agent.ran`. Its lease is given back at the stop, as for every run then, and its budget
  reserve stays charged until recovery closes it. Taking either up again belongs to
  `engine-adopts-runs-from-their-journals`.
- "Only records" means `event --add` and `lease --nack` (which has its own line, `{"nack": ...}`). They ask once and
  append to the journal when no engine answers. `act`, `lease --renew` and `item` wait as before.

Left for later (outside this gap): reading journals back after a restart (`engine-adopts-runs-from-their-journals`).
A restart in place leaves kept runs through the same `kill_all` path, but no test covers it. Under a systemd unit with
the default `KillMode=control-group`, `systemctl stop` of the service still ends the keepers in its cgroup; that is
not changed here. A call's line appended while the run holds half a line of its own joins it (said in SPEC 9.1).

Round 2, answering the review (its one finding: a kept run had no stop once its engine was gone).
- The timeout now holds with no engine: `keeper.launch` takes the block's timeout and writes it to the run's record as
  `wall` (timeout + `MARGIN`, 5 s); the keeper stops the group itself at it (SIGTERM, SIGKILL 2 s on), its exit's
  `how` is `timeout`. The margin keeps the engine's own timeout first while it is up (the existing tests'
  notes are unchanged); should the keeper's come first, the engine still notes it as the timeout. A `wall` that is
  not a positive finite number stops the keeper before the run starts (never unbounded). The compute worker's node
  runs write no `wall` and are unchanged. New test:
  `test_a_run_whose_engine_was_killed_still_ends_at_its_timeout` (engine SIGKILLed, the run and its child gone,
  `how: timeout`). It failed with the timeout not passed to the keeper, and passes with it.
- The other stops are narrowed in SPEC 9.1 rather than built, as a known limit (the more reversible choice: taking
  a left run up again is `engine-adopts-runs-from-their-journals`). With its engine gone, a new engine's
  `block --stop` does not know the run, no lease kill is made for it, and no budget trip happens (no engine reads its
  cost lines). Its spend is then bounded by its timeout, and for an `ai` block's own `claude -p` under `budget:` by
  its `--max-budget-usd`. A block with no timeout runs until it ends or `run --stop --runs`.

Round 3, answering the queue (two tests failed alone, both caused by this branch).
- `tests/test_upkeep_record.py::test_a_killed_compactor_releases_the_lock` replaces `stream.follow` with a function
  of four arguments, and the branch always passed a fifth (`leave`). With the setting off, the engine now calls
  `follow` with the same four arguments as before; only a kept run passes `leave`. This is what done item 5 asks.
- `tests/test_library_trust.py::test_every_compile_key_classified` found a new `self.keys(` site that was not
  classified. The scan named it `run` (the method it sat in). The `runs:` read is now its own `Compiler.runs`
  method, like `budget`, and the test's `by` table classifies `runs` as None (main or local file only, not a section
  a template writes). This adds one line to that test's table, which is the edit its own comment asks for
  ("a new self.keys( site: classify it here").
