# rs-calls: a run's calls to ergostat survive the engine restarting

depends-on: [rs-detach]

## Definition of done
- A run's calls (events, renew, nack, gated actions) retry with backoff across an engine restart, up to a bound (a setting, default 2 minutes), then fail as they do today.
- Each call carries an idempotency key, so a call in flight when the engine stopped is recorded once, a parked gated action included.

## Files to touch
The CLI's socket client, the engine's call handler, `tests/test_calls.py`.

## Acceptance tests
- `tests/test_calls.py::test_a_call_reconnects_across_a_restart`
- `tests/test_calls.py::test_a_call_in_flight_at_the_stop_is_recorded_once`
- `tests/test_calls.py::test_a_gated_action_in_flight_at_the_stop_is_asked_once`
- `tests/test_calls.py::test_a_call_past_the_bound_fails`

## Size budget
100 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Built (round 1), 59 net lines in `ergostat/calls/client.py`, `ergostat/calls/ops.py` and `ergostat/leases/acts.py`.
The decisions taken alone, each the most reversible one:
- **The setting** is an environment variable, `ERGOSTAT_CALL_RETRY` (seconds; default 120, at most 3600; unreadable
  means the default), not a model setting: the client reads no model. Only a run's call (`ERGOSTAT_SOCKET` set)
  retries; a command from a shell does what it did at once. Past the bound a call does what it does today with no
  engine (the command falls back to writing the record itself).
- **Retried** on: no socket, a refused connection, a connection reset or closed before a whole answer. A refusal, an
  `elsewhere` answer and a read timeout are not retried.
- **The key** (`"call"`, one per call, the same on every try) becomes the id of each event it records without one
  (the record already drops an id seen before), and the id of a renew's or nack's event. For `act`: a run with an item
  already finds its held action by action and arguments, so the key is used only when there is no `--key` and no
  item. `leases/acts.py` (outside the files named) takes an `id` for this: two lines.
- An `act` asked again after a restart waits its `wait` again from then.
- One more test beyond the four: `test_a_lease_call_asked_again_is_recorded_once`.

After the factory's unit run stalled (its output stopped at 18%, no failure printed): not reproduced here. Every
file whose runs call ergostat (`test_calls`, `test_leases`, `test_lease_kill`, `test_spec_engine`,
`test_program_actions`, `test_triggers2`/`3`, `test_resilience`, `test_gated_actions`, `test_daemons`,
`test_daemons_restart`) and every file with a `serial` test (a long one holds the whole parallel run back) passed alone
in its usual time; the whole suite was not run here. The likeliest cause, guarded against: an `ERGOSTAT_SOCKET`
inherited from an engine whose socket this machine can't reach (another machine's or container's path), so each
call waited the whole bound where it used to fall back at once. A call no longer tries again when the socket's folder
does not exist: an engine restarting keeps its state folder (or the short-path folder in the temporary directory),
so only a socket that can come back is waited for (`test_a_call_past_the_bound_fails`, checked to fail without it).

After the factory's second unit run stalled (its output stopped at 3%, no failure printed; not reproduced here, and the
whole suite was not run here): with every retry traced, the files run alone showed one call waiting on an engine
that had stopped for good (a daemon's `act` in `test_ticket_factory_daemons`, which was killed after 2 s). The earlier
guard, "the socket's folder exists", also falls short: every engine whose state path is long puts its socket in the
one shared `/tmp/ergostat-UID/`. So a run's socket inherited from an engine elsewhere (the factory's, which runs these
suites as a block) still waited the whole 2 minutes on each call. Now a call tries again only while the run's own state
folder (`ERGOSTAT_STATE_DIR` when the socket is its own, else the socket's folder) is here. Once the socket has been
removed (a clean stop) it waits `GONE` = 10 s at most for the socket to come back. A killed engine leaves its socket
behind, so its run gets the whole bound. This is my own call and the most reversible one: a restart (close, then exec)
that takes more than 10 s to listen again falls back as with no engine, as it does today. `test_a_call_past_the_bound_fails`
covers both rules and fails with either one removed (checked). Net lines outside tests and docs: about 74 of 100.

Round 2 (no review findings were handed over; main already merged in): a daemon's environment drops every
`ERGOSTAT_` variable not in `daemons/proc.py`'s `SHARED`, so the setting never reached a daemon's calls. It is now in
that list (one line, outside the files named; `test_a_call_past_the_bound_fails` asserts it). The suite's `home`
fixture now sets `ERGOSTAT_CALL_RETRY=5`, so a run or daemon that outlives its test's engine gives up after 5 s
instead of 2 minutes. That was the likely cause of the stalled unit runs. The retry tests give their own bound, and
on main the value was in effect 0. Not run here: the whole unit suite and the browser files. These were run one
file at a time and pass: `test_calls`, `test_warm`, `test_daemons`, `test_daemons_restart`,
`test_ticket_factory_daemons`, `test_leases`, `test_lease_kill`, `test_resilience`, `test_gated_actions`,
`test_program_actions`, `test_spec_engine`. Net lines outside tests and docs: about 75 of 100.

Round 3 (review rs-calls-1), finding by finding:
- **Blocking: the key was lost when the command fell back.** Now the command makes the key once (`cli/fast.py`
  `key()`) and passes it both to the socket call and to its own fallback: the event's id (`call-KEY.0`, the same id the
  engine gives it), the renewal's or nack's id, and the act's key. The act's key follows one rule for both paths
  (`ops.act_key`: the caller's `--key`, else this call's for a run with no item). New test
  `test_a_call_the_stopped_engine_recorded_is_recorded_once_by_the_commands_fallback`: the engine records the call and
  drops its answer, then is closed and not started again. The CLI falls back after `GONE` and the record holds one
  event, one renewal, one act. Each of the three asserts was seen to fail with its fallback's key removed. The nack's
  fallback uses the same key the same way, but no test covers it.
- **Not run by that reviewer.** These were run one file at a time here and pass: `test_calls`, `test_leases`,
  `test_gated_actions`, `test_program_actions`, `test_lease_kill`, `test_resilience`, `test_intake`, `test_storage`.
  ruff is clean.
- **`GONE` = 10 s narrows the 2-minute bound for a clean stop.** This departs from the definition of done: after a
  clean stop a run's call waits 10 s, not up to 2 minutes, before it falls back. It stays, as the most reversible
  choice. With the fallback now keyed, a restart slower than 10 s still records each call once, so what is lost is
  only the engine answering it rather than the command.
- **A repeated id returned the newly built event.** `leases/acts.py` (`again`), `intake/envelope.py`'s one-event path
  and the CLI's event fallback now return the stored event (its first time and seq). `envelope.py` is outside the
  files named (3 lines). `test_a_lease_call_asked_again_is_recorded_once` asserts it, and was seen to fail without it.

Not run here: the whole unit suite and the browser files. Net lines outside tests, docs and dev: 100 of 100 (131
added, 31 removed).

After round 3's unit run failed (its tail shows only `uv` building the package: no pytest line, no dot, and not even
`suite_watch`'s closing JSON line, so the log does not show what stopped it): not reproduced, and no code changed. The
whole unit suite, run here serially (`-p no:randomly`, 36 min), finished: 2333 passed, 69 skipped, 1 xfailed, 6 failed.
None of the six involves a call. Every one fails the same way: `AttributeError: module 'queue' has no attribute
'LifoQueue'` in a spawned process. `tests/test_backlog.py`, `test_factory.py` and `test_factory_times.py` put
`dev/bin` on `sys.path`, where `dev/bin/queue.py` hides the standard library's `queue` from every process spawned
after them in the same worker. They are `test_index_files.py` (4), `test_modelling_ai_cap.py::test_two_runs_cannot_both_take_the_last_of_the_cap`
and `test_store_conformance.py::test_a_second_instance_threads_and_processes_lose_nothing[sqlite]`. They depend on test
order, the branch touches none of these files, and the fault belongs to main (lesson 13): reported, not fixed here.
Every test's duration was checked for a wait on a call's bound (5 s, `GONE` 10 s, a 60 s read timeout), and no
call-related test shows one. The only tests near 60 s are `test_index_files`' four, which are the failures above, and
`test_factory.py::test_the_factory_model_loads` (60 s alone too). That one only reads the factory's model and makes
no call. ruff is clean.

After the factory's next unit run stalled (its tail: xdist up, 15 dots, then nothing; no failure printed): not
reproduced, because this session could run nothing (no shell: no tests, no ruff, no git, so this change is not
committed either). One defect was found by reading the engine's call handler, and it is fixed. When `Server.close`
ran while the parked-call thread was partway through a pass, close cleared `parked` (empty, since the thread had taken
the list out), and the thread then put its still-waiting calls back. Those connections were never closed, so their
callers did not see the stop and did not ask again. Each waited out its read timeout (a CLI `act`: its wait plus an
hour) instead of retrying across the restart, which goes against the first point of the definition of done for a
parked gated action. An `act` parked by a worker just after the close had the same gap. Now both go through
`Server._park`. Under `plock` it parks only while the socket is open (close clears `sock` before it takes `plock`),
and otherwise closes the connection so the caller asks again. The window is a whole pass of `settled` reads, which is
wide under load and narrow when tests run serially. That fits a stall seen only in the factory, but it is not shown
to be the stall's cause. No test puts the close in that gap yet. Budget: about 3 net lines over 100, because the fix
belongs in the call handler and nothing smaller closes the gap. Still open: a connection accepted around the close
and queued behind the workers' stop markers is never answered or closed. That predates this branch and is not
fixed here.

Round 4 (the finding handed over is review rs-calls-1's blocking one, answered in round 3: the command makes the key
once and its fallback records under it; nothing new beyond it). The previous session's uncommitted `Server._park`
change had been committed by the factory (`7e7554f0`). This round adds the test it lacked:
`test_a_gated_action_parked_while_the_engine_stops_is_asked_again` patches `program.settled` so the engine closes while
the parked-call thread is partway through a pass. It asserts the call is not put back on the stopped engine, then that
its caller asks the new engine, is parked there, is asked of the owner once, and runs once approved. With `_park`'s
`self.sock is not None` check removed, it fails (seen: the call left in `parked` of the closed engine). No code
changed this round. Run here, one file at a time, all passing: `test_calls` (14), `test_gated_actions`, `test_leases`,
`test_resilience`, `test_program_actions`, `test_daemons`, `test_lease_kill`; ruff is clean. Not run here: the whole
unit suite and the browser files. Budget unchanged: about 3 net lines over 100, for the reason given above.

After round 4's unit run stalled (its tail: xdist up, 73 dots, then nothing; no failure printed): not reproduced. The
call-related files and every file with a `serial` test (`test_watchdog`, `test_notify`, `test_parallel_runs`,
`test_daemons`, `test_daemons_restart`, with `test_calls`, `test_leases`, `test_lease_kill`, `test_resilience`,
`test_gated_actions`, `test_program_actions`, `test_spec_engine`, `test_ticket_factory_daemons`) passed together under
`-n 8 --dist worksteal` in 71 s (173 passed, 1 skipped). The whole suite was not run in parallel here (the house rule).
One thing in the suite fits a stall of every worker at once: `tests/conftest.py`'s run-wide lock. A `serial` test
holds it alone, so one serial test that hangs holds back all eight workers. Nothing here shows any serial test hangs.
Fixed this round, in the engine's call handler: the gap left open above. A connection accepted as `Server.close` ran
was queued behind the workers' stop markers and never answered or closed. Its caller then waited out its read timeout
(an `act`: its wait plus an hour) instead of seeing the stop and asking again, which goes against the first point of
the definition of done. `close` now clears `sock` under `plock`, and the accept thread queues a connection under
`plock` only while the socket is open; otherwise it closes the connection. So every connection is either queued ahead
of the stop markers (and answered) or closed. The accept thread also keeps its own reference to the socket, so `close`
can no longer turn it into `None` between the check and `accept()` (an `AttributeError` that killed the thread). New
test `test_a_call_accepted_as_the_engine_stops_is_closed_so_its_caller_asks_again` puts the close between the accept
and the hand-over. With the check removed it fails (seen: `TimeoutError` after its 20 s read timeout). It is not shown
to be the stall's cause. Run here, all passing: `test_calls` (15), `test_gated_actions`, `test_leases`,
`test_program_actions`, `test_resilience`, `test_lease_kill`, `test_daemons`, `test_spec_engine`, `test_watchdog`
(157 passed, serially in one process); ruff is clean. Not run here: the whole unit suite and the browser files.
Budget: about 7 net lines over 100. The 4 lines of this fix belong in the call handler, and nothing smaller closes the
gap. Refused this session: `env | grep -i ergostat` (to look for an inherited socket) and `git worktree add` of main
under /tmp (to compare test durations with main).

After round 4's second unit run failed (three `F`s at about 6%, 11% and 17%, then the output stops at 94%, mid-line,
with no pytest summary and not even `suite_watch`'s closing JSON line): no code changed, because no defect was found.
The log names no test, so `onmain.py` could rerun none. A log that ends with neither a summary nor the watchdog's line
means the suite was cut off from outside the suite (its container), not that pytest found a failure and ended. What
was run here, at this branch's head:
- Every test file, serially (`-p no:randomly`), in six chunks of files: all pass. The only failure seen was
  `test_recipes.py::test_the_schema_knows_contexts_and_a_blocks_context_and_review`, run from `tests/` by mistake (it
  opens a relative path), and it passes from the root.
- Two large subsets under `-n 8 --dist worksteal` and `suite_watch.py`. The first holds every file whose runs call
  ergostat, every file with a `serial` test, and the files order-dependent on main (`test_index_files`,
  `test_modelling_ai_cap`, `test_store_conformance`, `test_backlog`, `test_factory_times`): 490 passed, 1 failed;
  peaks of 405 threads, 172 processes, 1.3 GB. The second holds the factory, reload, shard, storage, sandbox and
  repair files: 488 passed. Neither stalled.
- The one failure, `test_runner_and_state.py::test_a_run_past_its_timeout_is_stopped_with_what_it_started`, is
  main's and not this branch's (lesson 13). It looks for `sleep 30` with `pgrep -f`, so under `-n 8` it finds another
  test's `sleep 30`. It then runs `lsof`, which this container does not have (`FileNotFoundError`). It passes alone.
- No test that makes a call took longer than its bound would explain. The slow tests (`test_backlog`'s and
  `test_factory`'s 60 s, `test_factory_join`'s 88 s, `test_reload_soak`'s 127 s) load the factory's model or poll
  HTTP, and make no call.
Not found, so not fixed: which three tests failed, and what cut the run off. The order-dependent failures on main
(the `queue` hidden by `dev/bin/queue.py`, above) fit the three `F`s, but that is not shown. The suite container's
limits (12 GB, 4096 pids, a 2 GB tmpfs `/tmp`, 4 CPUs) are candidates. This session found `/tmp` already 561 MB full
after only some of the serial chunks: 268 MB of it from one test of main's,
`test_index_files.py::test_two_processes_one_tidying_never_corrupt_an_index_another_has_open`. A whole parallel run
keeps every test's `tmp_path`, so it may outgrow a 2 GB `/tmp`. Neither is shown. Refused this session: the whole
unit suite run serially in the background (with and without `suite_watch.py`), `taskset -c 0-3` (to run under the
container's 4 CPUs), and a `du` of `/tmp`'s pytest folder piped through `sort` and `wc`.
Budget unchanged: about 7 net lines over 100. ruff is clean.

Round 5 (the finding handed over is again review rs-calls-1's blocking one, answered in round 3). Main
(`20339898`) is merged in (`0fe917fa`), and the fix survives the merge: `cli/record.py`, `cli/leases.py` and
`cli/gated.py` each make the key once with `fast.key()` and pass it to both the socket call and their own fallback.
No code changed this round. Run here at the branch's head, one batch of files at a time, serially
(`-p no:randomly`), all passing: `test_calls`, `test_gated_actions`, `test_leases`, `test_resilience`,
`test_program_actions`, `test_lease_kill` (116 passed), then `test_daemons`, `test_daemons_restart`,
`test_spec_engine`, `test_ticket_factory_daemons`, `test_warm` (71 passed). ruff is clean. Not run here: the whole
unit suite and the browser files. Budget not recounted this round; it is unchanged since round 4 (about 7 net lines
over 100). Refused this session: a `git diff --numstat` piped through `awk` to recount the budget, which was
chained after the second test batch (the batch was then run alone).

After round 5's unit run failed (its tail: xdist up, then dots to 75%, mid-line, with no pytest summary and no
`suite_watch` JSON line): not reproduced. No code changed, because reading found no defect. What the tail shows,
going by the factory's own code:
- `agents.suites` gives the suite no timeout of its own, so the run either ended by itself or was killed.
  `suite_watch` turns a SIGTERM into a clean stop that still prints its JSON line (`_interrupted`). A log without that
  line means `suite_watch` died by SIGKILL: either the suite container was killed (`agents.killed`, after the
  implementor was stopped or raised) or the memory cgroup's OOM killer stepped in. The suite's `rc` and the
  container's `OOMKilled` would tell which, and neither can be seen from this worktree.
- A hung test of the branch could stall every worker only through `tests/conftest.py`'s run-wide lock. A `serial`
  test waits to hold that lock alone, so a hung test holding it shared blocks each worker as that worker reaches a
  serial test. That cannot explain the earlier run that stopped after 15 dots, before most workers reach any serial
  test. A serial test that hung while holding the lock alone could. The serial files (`test_daemons`, `test_notify`,
  `test_parallel_runs`, `test_watchdog`) passed here in 66 s (36 passed, 1 skipped). The slowest test took 8.5 s, and
  none waited out a call's bound.
- Every retry ends. `call` gives up at its bound: 5 s under the suite's `home` fixture, and 2 minutes only where a
  test strips every `ERGOSTAT_` variable, which strips the socket too, so nothing retries. No loop in `client.py` or
  `server.py` waits without a deadline, and nothing new holds `plock` across a wait (the job queue is unbounded).
Run here, one file or batch at a time, all passing: `test_calls` (15), then `test_resilience`, `test_lease_kill`,
`test_daemons_restart`, `test_gated_actions` (66), then `test_notify`, `test_parallel_runs`, `test_daemons`,
`test_watchdog` (36 passed, 1 skipped). ruff is clean. Not run here: the whole unit suite and the browser files.
Budget unchanged (about 7 net lines over 100). Refused this session: `git worktree add --detach /tmp/rsmain main`
(to compare timings with main); test files a to i under `-n 8` with `suite_watch.py` and
`-o faulthandler_timeout=240` (to catch a hung test's stack); `ps -A -o pid,ppid,etime,rss,command` after the
restart tests (to look for processes they leave behind); and a heredoc append to this file chained with the commit.
The next step needs the factory: the failed run's `rc`, its container's `OOMKilled`, and one unit run with
`-o faulthandler_timeout=300`, which prints the stack of any test still running after 5 minutes.

After round 5's second unit run failed (its tail: two `F`s at about 14% and 16%, then dots to 98%, mid-line, with no
pytest summary and no `suite_watch` JSON line): not reproduced, and no code changed, because no defect was found.
This session ran every test file in parallel for the first time, the way the factory runs them (`suite_watch.py`,
`-n 8 --dist worksteal`, random order), in three alphabetical chunks:
- `tests/test_[a-f]*.py`: 957 passed, 4 skipped, 414 s. Peaks: 168 threads, 948 MB, 26 processes.
- `tests/test_[g-q]*.py`: 723 passed, 5 skipped, 1 xfailed, 190 s. Peaks: 157 threads, 1.3 GB, 38 processes.
- `tests/test_[r-z]*.py`: 824 passed, 60 skipped, 148 s. Peaks: 400 threads, 1.5 GB, 164 processes.
No failures, nothing killed, nothing left behind, 2504 tests in all (about as many as the factory's run). `/tmp` held
505 MB of its 2 GB afterwards. The two `F`s therefore come from something these runs lack: the whole suite in one run
(so test order across files: main's `dev/bin/queue.py` hiding the standard `queue`, above, fits) or the suite
container's 4 CPUs (this machine has 24). Neither is shown.
What reading ruled out this round: the factory's `fac.suite` strips every `ERGOSTAT_` variable, so no inherited
socket reaches the suite, and the `home` fixture is autouse, so every run a test starts gets the 5 s bound. Nothing
in `agents.suites` or `resources.sampled` kills a suite, and `suite_watch` prints a line before it kills one (none in
the tail). The output cut mid-line with nonzero `rc`, from a container started with `--init`, fits the container
being SIGKILLed as a whole (OOM against its 12 GB, with tmpfs `/tmp` counted, or `docker kill`) better than any hang.
Refused this session: `uv run python -c "import os; print(sorted(k for k in os.environ if k.startswith('ERGOSTAT')))"`,
an `ls tests/test_*.py | sed ...` splitting the files into lists under `/tmp`, and
`taskset -c 0-3 uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal tests/test_[r-z]*.py 2>&1 | tail -25`
(the 4 CPUs of the suite container). The next step still needs the factory: the run's `rc`, the container's
`OOMKilled`, the names behind the two `F`s (`fac.failed_tests` of the whole log, not of its tail), and one run with
`-o faulthandler_timeout=300`. Budget unchanged: about 7 net lines over 100.
