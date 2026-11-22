# dod-measured-runs: the factory runs a definition's acceptance measurement that sessions cannot
depends-on: []

## Definition of done
- A factory command (dev/bin, e.g. `measure-runs GAP`) runs a parked or built gap's named acceptance measurement on its branch head: N runs (N capped, hard maximum 50, enforced at parse and run time) of a pytest selection under `scripts/suite_watch.py`, through the shared suite slot, optionally with the CPU loaded by a capped, watchdogged load (kill past 1,500 threads or 6 GB).
- Each run's rc and, for a failure, its traceback tail are recorded; the counts (passed/failed of N, head sha) are appended to the branch's record where review reads them, and the gap is sent back to review unchanged when all pass, or to fix with the failing traceback as its input when any fail.
- A run that cannot be read or was killed counts as a failure (never as a pass).
- dev/README.md (The pipeline manager) and the agent guide say when to use it; the first user is gap/lease-shutdown-race (30 loaded runs of -n 8 tests/test_leases.py).

## Acceptance tests
- tests/test_factory_measure_runs.py::test_counts_recorded_and_sent_to_review_when_all_pass
- tests/test_factory_measure_runs.py::test_a_failing_run_sends_the_gap_to_fix_with_its_traceback
- tests/test_factory_measure_runs.py::test_n_above_the_cap_is_refused
- tests/test_factory_measure_runs.py::test_a_killed_or_unreadable_run_counts_as_failed
(each with stand-in suites, no real load)

## Size budget
180 net lines outside tests and docs

## Where it stopped

Round 1, built. One thing is not run here: the first real use, the 30 loaded runs for gap/lease-shutdown-race.

- **What was built.** `python3 dev/bin/manage.py measure-runs GAP --runs N --tests "T" [--load K] [--why W]`. The
  tool is in manage.py, so the pipeline manager can call it as well as the coordinator. The runs are in a new module,
  `dev/bin/runs.py`. The command makes N runs of `[suites] measure` (under `scripts/suite_watch.py`), each through
  `fac.suite`, which puts it in the `[suites] slot`. They run in a clone of the drop at the branch head, in a suite
  container unless the AI is the stand-in. With `--load K`, `[suites] load` runs K busy processes (forks of one
  `python3 -c`) under a `suite_watch.py` of their own. That load gets its own container when not the stand-in. Its
  process group is SIGTERMed, then SIGKILLed, in a `finally`. The counts are appended to the gap's `measured_runs`
  (a new `append` fold in ergostat.yaml) and said in its `findings`. If every run passed, the gap gets `gap.built`
  at the same head, so review takes it again. If any failed, it gets `gap.sent-back` (`sent_back_by: measure-runs`,
  one failed gate, one fix round), with the first failing run's log tail as a finding. The call is also recorded as an
  intervention of class `operator-decision`, so the watch does not raise it as a defect.
- **Caps.** N is 1-50 and K is 1-8. Both are checked by the parser (`runs.count`, `runs.procs`) and again in
  `runs.measure`. The loop also stops at `min(n, 50)`. The selection is an allowlist: test files or ids under
  `tests/` (no `..`), and at most one `-n` of 1-8 (CLAUDE.md's unit worker count). Each run gets `-p no:randomly`.
- **Reading a run.** A run passes only if the shell's exit is 0 and the last `{"rc"...}` line of suite_watch says
  rc 0, `killed` null and no worker killed. Everything else is a failure: a missing or unreadable log, no watchdog
  line, a watchdog kill. A run that was never made also counts as failed (`failed = n - passed`).
- **Decisions taken alone (reversible).**
  - The measurement is given on the command line, as the definition names it. It is not parsed out of the
    definition's prose: those sentences have no fixed form yet.
  - "The branch's record where review reads them" is taken to be the gap's `findings`, which the reviewer's brief
    shows, plus `measured_runs` for the full record. Nothing is committed to the branch, so its head stays the head
    that was measured.
  - A built gap can be taken by the reviewer during a long measurement. To catch that, the gap's state and its branch
    tip are read again before the gap is moved (lesson-1). If the gap left parked or built, or its branch moved, the
    counts are recorded alone (`gap.measured`), the gap is not moved, and the call is refused. That second read takes
    no lock, because the engine's takes have none to share, so a take that lands between the read and the write is
    still missed. dev/README.md says so.
  - A failed measurement counts one failed gate. It does not park the gap on the kill rule itself: the next review
    does that.
- **Size.** By the factory's own count (`fac.net_lines`, which leaves out dev/ and ergostat.yaml), this is 4 lines:
  the CLAUDE.md paragraph. Counting dev/ too, the code is 190 lines (runs.py 149, manage.py 36, factory.toml 4,
  ergostat.yaml 1), 10 over 180. The overrun is docstrings and comments that state the caps and the fail-closed rule.
- **Tests.** The four acceptance tests are written, plus a fifth, `test_a_branch_moved_during_the_runs_keeps_the_gap_where_it_is`
  (lesson-1: a stand-in run moves the branch partway). The tests use a stand-in suite that plays a planned outcome
  per run and a stand-in load that only sleeps. They are marked slow, about 20 s each, because of the fixture's build.
  For lesson-9, I broke each guarded part and watched its test fail:
  - no watchdog line read as a pass: `test_a_killed_or_unreadable_run_counts_as_failed` failed;
  - the load's stop removed: `test_counts_recorded_and_sent_to_review_when_all_pass` failed (the sleeper was still
    alive);
  - the branch re-check removed: the fifth test failed;
  - the run-time cap removed: `test_n_above_the_cap_is_refused` failed;
  - the traceback dropped from the fix input: `test_a_failing_run_sends_the_gap_to_fix_with_its_traceback` failed.
- **Not run here.** The real 30 loaded `-n 8 tests/test_leases.py` runs, and any real load (the definition asks for
  stand-ins only). Neither the unit suite nor the browser files were run in parallel: the factory runs those. This
  clone has no origin remote, and local `main` has nothing the branch lacks, so there was nothing to merge in.
- **After the fast suites (round 1).** The factory's `unit` run ended at 66% with no failing test named and no
  closing line from the watchdog. That looks like the run or its container was killed, not like a failing test. The
  five tests of tests/test_factory_measure_runs.py pass alone (5 passed, 90 s). Reading the code found one defect, in
  `runs.loaded`: after the SIGTERM wait reaped the load's leader, the code still sent SIGKILL to that group id, which
  could by then belong to another process (lesson-6). It is fixed: SIGKILL now goes only to a group whose leader is
  still unreaped. I could not show that this defect caused the cut-off, because the watched parallel run of the new
  file was refused here. The factory's next unit run is the check.

### Round 2

Main (e1e778c1) is merged in. The conflict in dev/bin/manage.py was the `CLASSES` table and the dispatch table:
main's `propose` and `ask` and this branch's `measure-runs` are all kept. Both blocking findings are answered. The
review listed no non-blocking ones.

- **Finding 1: parked gaps moved without continue_gap's checks.** `manage.measurable` now refuses three kinds of
  parked gap. The first is one already resumed (`resumed_as` set). The second is one whose branch another live gap
  holds; this uses `holders`, which is now shared with `continue_gap`. The third is one whose `parked_for` is not in
  the allowlist `MEASURED_PARKS = ("needs", "defect")`, or that is marked `deferred` or `cancelled`. So deferred,
  cancelled, kill-rule, waits_on and split parks are refused, and so is a park with no kind said. The check runs
  before the runs. It runs again after them, under the continue lock that `continue` and the park resumer take,
  together with the state and branch re-read and the write. A park continued while the runs ran is caught there:
  its counts are recorded alone and the gap stays parked. New test: `test_a_park_a_measurement_cannot_clear_is_refused`.
  It covers each refused kind, a held branch, and a resume that lands mid-run (the stand-in suite writes `resumed_as`
  into the record), then shows that a `needs` park is accepted. Decision taken alone (reversible): the allowlist is the
  review's own example, `needs` and `defect`. A coordinator who wants another kind measured can widen the tuple.
- **Finding 2: the load had no end of its own.** `runs.loaded` now touches a heartbeat file, `.git/measure-beat` in the
  clone (`/work/...` in a container, through the mount), every stale/6 s from a thread. The `[suites] load` program
  stops each busy process once that file is gone or has not changed for `{stale}` s. That is `[suites] load_stale_s`,
  default 30, bounded to 1-300. The load measures staleness by its own monotonic clock, not against the host's mtime,
  so clock skew between host and Docker VM does not matter. With this, a SIGKILL to manage.py or manager.py stops the
  touching, and the load ends within about `load_stale_s`. A removed clone ends it at once. manage.py now calls
  `fac.stop_on_term()`, so a SIGTERM by hand runs the finally. A run during which the load had ended counts as failed
  ("the load had ended"), so an unloaded run never passes as a loaded one (lesson-3). New tests:
  - `test_the_load_ends_on_its_own_when_its_caller_is_killed`: a stand-in load that honours the beat stays alive past
    its stale time while manage.py lives, then ends after manage.py is SIGKILLed.
  - `test_the_real_load_ends_without_its_beat`: the real `[suites] load` command from dev/factory.toml, 2 processes,
    stale 1 s, ends with rc 0 both with its beat file missing and with it never touched.
  - An added case in `test_a_killed_or_unreadable_run_counts_as_failed`: a load that exits at once makes its run fail.

  dev/README.md now says exactly which ends stop the load (normal end, error, SIGTERM, and on its own within
  `load_stale_s` otherwise), and which parks are measured.
- **Breaks (lesson-9).** I broke each new guard and watched its test fail:
  - park-kind allowlist removed: the park test failed;
  - re-check under the lock removed: the park test's mid-run resume failed;
  - branch-held check removed: the park test failed;
  - beat not touched: the caller-killed test failed (the load died while its caller lived);
  - real load loop made endless: the real-load test timed out;
  - the load-ended check removed: the killed-or-unreadable test failed.
- **Size.** This round adds 71 net lines in dev/: manage.py +40, runs.py +18, factory.toml +13 (the load program is
  now multi-line). That brings the code in dev/ to about 261 lines. By the factory's own count, which leaves out dev/,
  it is still 4. The overrun past 180 is the two review fixes: the park checks and the heartbeat with its load program.
- **Run here.** `tests/test_factory_measure_runs.py`: 8 passed, alone, serially. `tests/test_factory_manager.py`:
  32 passed, since `continue_gap` now shares `holders` and the lock helper. ruff is clean. **Not run here:** the unit
  suite, the four browser files and any real 30-run load. The factory runs those.

### Round 3

Main (7c46bc6d) is merged in. Its only conflict was in dev/factory.toml `[suites]`. Main had added `-rs` to `rerun`,
and the branch had added `measure`, `load` and `load_stale_s` next to it. Both are kept: main's `rerun` line and
the branch's three keys. This round changes no code. The queue's finding (the conflict with main) is the only one
listed, and it is answered by this merge.

- **Run here, after the merge.** `tests/test_factory_measure_runs.py`: 8 passed (this includes the test that runs the
  real `[suites] load` read from the merged dev/factory.toml). `tests/test_factory_manager.py`: 33 passed. ruff is
  clean. **Not run here:** the unit suite, the four browser files and any real 30-run load. The factory runs those.
- Overrun reason: the code in dev/ is about 261 net lines, 81 over 180. The overrun is round 2's two review fixes: the
  park checks under the continue lock, and the load heartbeat with its multi-line load program. The factory's own
  count, which leaves out dev/, is 4.

### Round 4

Review 3 had one blocking finding and three non-blocking ones. All four are answered below (lesson-12).

- **Blocking: another process's sweep removed the load past 70 min.** The load's container is now named with its own
  role, `measure-load`. `agents.contained` takes a `role`, which defaults to `suite`. `agents.TIMEOUTS["measure-load"]`
  is 43,200 s (12 h). That value is also `runs.WALL`. So another process's `sweep()` leaves the load alone for 12 h
  10 min, not 70 min. The measurement's wall time now has a bound. Before each run, if the time so far plus the longest
  run so far would pass `WALL`, no more runs start. Each run not started is recorded as failed ("not started: past the
  43200 s wall bound"), so the load never has to outlive its sweep time. A leftover load is still swept after
  12 h 10 min. Its heartbeat ends it well before that anyway. Each run's own container keeps the `suite` role, so one
  run longer than 70 min may be swept, and it then counts as a failure. dev/README.md says all of this. Decision taken
  alone (reversible): 12 h. That covers 30 runs of up to 24 min each, and 50 of up to 14 min.
  New tests:
  - `test_the_load_survives_another_process_s_sweep`: the real `runs.loaded`, with docker stood in. The load's name is
    taken out of RUNNING, as it would be in another process. A sweep then removes a 2 h old suite container but leaves
    an 11.5 h old load, and it removes a 13 h old load.
  - `test_no_run_starts_past_the_wall_bound`: with WALL at 1.5 s and 1 s runs, 1 run is made and the other 2 count
    as failed.
- **Non-blocking: `needs` parks were cleared whatever they needed.** `manage.measurable` now refuses a `needs` park
  unless its `parked_until` action has a word starting with "measure". A need for an approval, or with no action said,
  is refused. The park test checks both cases, and it checks that a need naming `measure-runs` is accepted.
- **Non-blocking: only the SIGKILL path of the load had a test.** New test: `test_the_load_stops_with_its_caller_on_sigterm`.
  It uses a load that never reads its beat, so only the finally's process-group stop can end it. After a SIGTERM to
  manage.py, the load and the hanging suite are gone within 5 s. My first version used the beat-reading stand-in load.
  It still passed with the stop removed, because the clone's removal deletes the beat. That is why the load here is
  deaf to it.
- **Non-blocking: the moved() window.** This stays as it is. Closing it would take a lock shared with the engine's takes,
  and that is outside this gap. The window is one record read wide, and dev/README.md says so.
- **Breaks (lesson-9).** I broke each guard and watched its test fail:
  - the load's role set back to `suite`: the sweep test failed;
  - the wall check disabled: the wall test failed;
  - the needs check disabled: the park test failed;
  - the finally's stop loop emptied: the SIGTERM test failed (the deaf load was still alive).
- **Run here.** `tests/test_factory_measure_runs.py`: 11 passed. `tests/test_agents.py` and
  `tests/test_factory_manager.py`: 49 passed. ruff is clean. **Not run here:** the unit suite, the four browser files
  and any real 30-run load. The factory runs those. No main merge this round: local `main` has nothing new.
- Overrun reason: the code in dev/ is about 279 net lines, 99 over 180. Round 4 adds about 18 (the measure-load role,
  the wall bound, the needs check) on top of round 2's two review fixes. The factory's own count, which leaves out
  dev/, is 4.

### Round 5

Review 4 had one blocking finding and three non-blocking ones. Each is answered below (lesson-12).

- **Blocking: the manager's measurement ran inside its 1 h block.** It no longer does. When the pipeline manager calls
  `measure-runs` (manage.BY is `pipeline-manager`), manage.py runs no runs. It checks the call as it would be checked
  when run: the parser's caps, then `measurable` on the gap. Then it asks for the new gated action `manager-measure`
  (dev/model/manager.yaml, `gate: approve`, `timeout: 13h`, listed in the block's `actions`), and records the ask as an
  intervention, `held`, like `close` and `park`. The manager's session ends at once. Once the coordinator approves,
  ergostat runs the action's command outside the block. That command is the same `manage.py measure-runs` with the
  same arguments, now as the coordinator, with a 13 h timeout, which is past `runs.WALL` (12 h). The coordinator's own
  call by hand runs at once, as before. The prompt, dev/README.md and CLAUDE.md say which path is which. The prompt no
  longer says "it runs for as long as the runs take" of the session. `--load 0` now parses as no load, because an
  action's arguments cannot be empty. Decision taken alone (reversible): the measurement waits for the coordinator's
  approval. I did not give it a block of its own, because an approval is the smallest change, and the ladder can move
  the `measure` class to AI or to a program later. The approved command runs in the process that carries out the
  approval (the engine's thread, or the process the approval was given in). That process waits for it, and
  dev/README.md says so.
  New test: `test_the_manager_s_measurement_is_asked_not_run_inside_its_block`. It runs manager.py with a stand-in
  answer that calls `measure-runs`. The action is held, no run is made, no load is started and the gap stays built.
  The test then fills the model's own `manager-measure` template with the asked arguments, using `gate.render` and
  its shell quoting. It runs that command and sees 2 of 2 runs pass at the head, with `-n 8 tests/test_leases.py`
  reaching the suite whole. It also checks that the action's timeout is greater than WALL, which is greater than the
  block's timeout. Last, it checks that a kill-rule park is refused at ask time, with no action asked.
- **Non-blocking: a single run had no wall time of its own.** It has one now. Each run is bounded by the time left of
  `runs.WALL`. `runs.deadline` sets a SIGALRM that raises `Late` inside `fac.suite`, whose finally kills the run's
  process group, and runs.py's finally kills its container. The run counts as failed ("stopped: past the ... wall
  bound"), and no other run starts. So a hung run no longer holds the slot and the load until some other process's
  sweep. The whole measurement ends within WALL, inside the action's 13 h. One limit: the signal reaches only the main
  thread, and off it the run has no bound. manage.py's runs are on its main thread. New test:
  `test_a_run_that_hangs_is_stopped_at_the_wall_bound`. With WALL at 2 s, a stand-in that sleeps 60 s is stopped and
  its process is gone, and the second run is not started.
- **Non-blocking: start_new_session, so an engine killpg of the caller does not reach a run in progress.** This stays.
  On SIGTERM the finallies stop the run and the load (tested in round 4). On SIGKILL the load ends by its heartbeat.
  A run in progress then carries on to its own end, or to the 70 min sweep of its `suite` container, so it is
  bounded. Its own new session is what lets `fac.suite` kill its whole group. The manager path no longer runs
  measurements, so the engine's block timeout can no longer cause this.
- **Non-blocking: not run by the reviewer.** Noted. The runs made here are listed below.
- **Breaks (lesson-9).** I broke each guard and watched its test fail:
  - measure-runs run in-process from the manager again: the manager test failed (the gap went to fix in the block);
  - the ask-time `measurable` check removed: the manager test failed (a kill-rule park was asked for);
  - `deadline` made a no-op: the hang test failed (the run was read as exit 0 after its 60 s sleep, not stopped).
- **Run here.** `tests/test_factory_measure_runs.py`: 13 passed. `tests/test_factory_manager.py`: 33 passed. That was
  before the runs.py change, which that file does not use. `uv run ruff check ergostat tests scripts` is clean, and so
  are dev/bin/runs.py and dev/bin/manage.py. `ruff check dev/bin` finds 2 errors, in plan.py (B023) and review.py
  (E501). This branch touches neither file. **Not run here:** the unit suite, the four browser files and any real
  30-run load. The factory runs those. No main merge: local `main` has nothing the branch lacks.
- Overrun reason: the code in dev/ is about 319 net lines, 139 over 180. Round 5 adds about 40: the gated
  manager-measure action (manage.py +5, manager.yaml +8) and the per-run wall bound (runs.py +27). Both answer review
  4's findings, on top of rounds 2 and 4's review fixes. The factory's own count, which leaves out dev/, is 5.

### Round 6

Review 5 had one blocking finding and three non-blocking ones. Each is answered below (lesson-12).

- **Blocking: the approved 12 h measurement ran inline in gate.approve, so the approver waited.** It no longer does.
  The `manager-measure` command is now `manage.py measure-runs GAP --detach ...`, and its timeout is 2 min. With
  `--detach`, manage.py checks the call again (the parser's caps, then `measurable`). It then starts the same
  `measure-runs` as a new process in a session of its own: stdin is /dev/null and output goes to
  `run/measure/*-detached.txt`, so it has no terminal and is outside the approver's process group. Then it returns at
  once. The action is recorded `ran`, with the measurement's pid and log. So an `actions --approve` terminal, a web
  worker thread or the engine is held for about a second, not 12 h. A Ctrl-C to the approver, or the web server
  exiting, cannot reach the measurement, and the action does not stay `approved, running`. The measurement records its
  own end. On success, those are the counts and the move, as before. On a refusal or failure, it is an intervention
  with `ended` and the reason, for example when the park was continued while the runs ran. So an approved measurement
  never ends unrecorded. If the gap is no longer measurable when it is approved, the action is recorded `failed` and no
  run is made. The measurement is still bounded by `runs.WALL`, with its load ended by its heartbeat as before.
  Decision taken alone (reversible): detach in manage.py rather than change ergostat's `gate.approve`, which is outside
  this gap. One limit is left: a SIGKILL to the detached measurement itself, by someone, leaves no end recorded. The
  launch is in the action's output (pid and log), and the load still ends by its heartbeat.
  The test `test_the_manager_s_measurement_is_asked_not_run_inside_its_block` now approves through the real
  `gate.approve`, in an ergostat project whose action is the model's own `manager-measure` template. It shows:
  - approve returns with the action `ran` while the measurement is still running, in a session of its own;
  - the measurement then records 2 of 2 passed at the head, the gap built;
  - its intervention is by `pipeline-manager` with `asked_as` the action's id;
  - an approval of a resumed park fails the action, with no run made;
  - a park resumed mid-run leaves the gap parked, and an `ended` intervention says "recorded alone".
- **Non-blocking: the approved run was attributed to the coordinator.** The detached run is given `--asked-as` set to
  `$ERGOSTAT_ACTION`. With it, BY is `pipeline-manager`, its asker, and the intervention carries `asked_as`, the
  action's id. Only the coordinator's own process can pass `--asked-as`: a call from the block's run is gated before
  that flag is read.
- **Non-blocking: runs.deadline had no bound off the main thread.** It now fails closed. `runs.measure` refuses (a
  ValueError) before making any run when it is not on the main thread, and `deadline` raises if it is ever entered
  there. The hang test now also calls `runs.measure` from a thread and sees it refused, with no run made.
- **Non-blocking: the "Run here" list ran test_factory_manager.py before the runs.py change.** Rerun at this round's
  head: 33 passed. The unit suite and the four browser files are still not run here. The merge queue runs them
  (lesson-7).
- **Breaks (lesson-9).** I broke each guard and watched its test fail:
  - the detached start made to wait for its measurement: the manager test failed (the measurement was over when
    approve returned);
  - the `ended` intervention on a refusal removed: the manager test failed;
  - the detached run attributed to the coordinator again: the manager test failed;
  - the off-main-thread check in `runs.measure` removed: the hang test failed.
- **Run here.** `tests/test_factory_measure_runs.py`: 13 passed. `tests/test_factory_manager.py`: 33 passed.
  `uv run ruff check ergostat tests scripts dev/bin/manage.py dev/bin/runs.py` is clean. Local `main` is already in
  the branch. **Not run here:** the unit suite, the four browser files and any real 30-run load.
- Overrun reason: the code in dev/ is about 356 net lines, 176 over 180. Round 6 adds about 37 (manage.py's detached
  start and its recorded end, 36; runs.py's thread check, 1), answering review 5. That comes on top of the review
  fixes of rounds 2, 4 and 5. The factory's own count, which leaves out dev/, is 6.

### Round 7

Review 6 had one blocking finding and one note. Both are answered below (lesson-12).

- **Blocking: a SIGTERM to the detached measurement ended it unrecorded.** `manage.asked` now also catches a
  BaseException: stop_on_term's SystemExit(143), or a Ctrl-C. By the time it is caught, the finallies have already
  stopped the run and the load. It ignores any further SIGTERM, records an intervention `ended: stopped` with
  `asked_as` ("stopped by SIGTERM before its runs ended: no counts, the gap untouched"), and raises again. `manage.run`
  now raises a SystemExit(143) again instead of calling it "refused: the call does not parse", so the process exits
  143. dev/README.md, and the round-6 claim above, now say it plainly: a SIGTERM or Ctrl-C records the end, and only a
  SIGKILL leaves it unrecorded (the load still ends by its heartbeat). The counts of the runs made before the SIGTERM
  are not kept: `runs.measure` returns only when it ends. The gap is not moved.
  New test: `test_a_sigterm_to_the_detached_measurement_records_its_end`. It approves the model's `manager-measure`
  through the real `gate.approve`, with a hanging stand-in suite and a load, and SIGTERMs the pid the action's output
  gives. It then checks four things:
  - the measurement, its run and its load are all gone;
  - one intervention says `ended: stopped`, SIGTERM, and `asked_as` the action's id;
  - the detached log does not say "does not parse";
  - the gap is still built, with no counts.
- **Note: not run by the reviewer.** Noted. The runs made here are listed below.
- **Breaks (lesson-9).** I broke each new guard and watched the test fail:
  - the new handler narrowed to KeyboardInterrupt: no `ended` intervention was found;
  - the 143 re-raise in `run` disabled: the log said "refused: the call does not parse (143)".
- **Run here.** `tests/test_factory_measure_runs.py`: 14 passed. `tests/test_factory_manager.py`: 33 passed.
  `uv run ruff check ergostat tests scripts dev/bin/manage.py dev/bin/runs.py` is clean. Local `main` has nothing the
  branch lacks. **Not run here:** the unit suite, the four browser files and any real 30-run load. The merge queue
  runs those.
- Overrun reason: the code in dev/ is about 366 net lines, 186 over 180. Round 7 adds 10 in manage.py (the recorded
  end on a SIGTERM and the 143 re-raise), answering review 6. That comes on top of the review fixes of rounds 2, 4,
  5 and 6. The factory's own count, which leaves out dev/, is 6.
