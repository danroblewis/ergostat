# warm-failed-runs-charged: Warm runs that crash or hang report their CPU

depends-on: []

Audit 2026-11-21, reproduced: warm runs are charged only on `done` (`ergostat/daemons/proc.py`), so a crashed or hung run has no `resources` after burning CPU. These are often the costliest runs, and GAPS says each run is charged.

## Definition of done
`fail_all` and the timeout path charge each run what it used, or record it as unknown when it cannot be read.

## Files to touch
`ergostat/daemons/proc.py`, the warm daemon tests.

## Risks
- lesson-3: unknown is recorded as unknown, never zero.

## Acceptance tests
- `tests/test_daemons.py::test_a_crashed_warm_run_is_charged`
- `tests/test_daemons.py::test_a_timed_out_warm_run_is_charged`

## Size budget
25 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built (round 2). 7 net lines of code outside tests and docs (`proc.py` +4, `usage.py` +3), within the budget of 25.

Round 2 answers to the queue and to review 1:
- Queue: `tests/test_spec_auxiliaries.py::test_a_memoryless_setting_stays_an_auxiliary_the_block_states_whole`
  failed for the queue, both in a batch and alone. It passes here, alone and with its whole file, on this branch after
  merging main (6ad359c0, which includes the other branch of that batch). Its blocks have no `daemon:`, and only a
  daemon's block reaches `daemons.run_item`, so the code this branch changes is not on its path. It is reported
  (lesson-13), not fixed here. If it fails again, it should be run on clean main.
- Review 1, lesson-1: `test_a_warm_run_failed_between_its_done_s_charge_and_its_pop_is_charged_and_ended_once` puts
  `fail_all` between the `done` path's charge and its pop, using a stand-in `charge`. With the `is not h` guard
  removed it fails ("fail_all's charge kept, never done's written over it"). It passes with the guard.
- Review 1, the double return: `charge()` now returns only the run's resources and the members it left running. The
  recycle reason is worked out inside the lock in the `done` path, so `served` is read there under the lock.
  `fail_all` takes only the resources; its process is being replaced anyway.

Not run here: the whole unit suite and the four browser files. The factory runs them under the watchdog. Main was
merged as the local `main` (6ad359c0); origin was not fetched (no network).

Round 3 (answers to review 2). Still 7 net lines of code outside tests and docs (`proc.py` +4, `usage.py` +3).
- Review 2, lesson-13: commit 7eb9e82c is undone. `git revert` was refused in this session, so its four hunks were
  reversed by hand in a new commit. `proc.py` is now the same as it was before 7eb9e82c
  (`git diff 7eb9e82c~1 -- ergostat/daemons/proc.py` is empty). The flake is reported here for a gap of its own:
  `tests/test_daemon_observations.py::test_a_reads_observations_are_judged_at_the_time_it_was_read` can fail under
  load. The test's own `chunk()` call and the reader thread's reads (heartbeats) both write `Process.read_at`. A read
  in the middle moves the test's remaining lines to a later clock. This code is main's (from daemons-left-over), so
  the test can fail on main too. A fix that looked right was to pass a local `at` from `chunk()` into `line()`. It
  passed here (10 passed alone after the revert as well; the race needs load).
- Review 2, the stale 'Where it stopped': this section describes round 3.
- Review 2, Process-level test: `test_a_warm_run_s_resources_say_which_read_failed_and_hold_no_cpu` calls
  `Process.charge` with a reaped leader whose rusage is unknown. It checks the whole resources dict, and so the
  message and the absent `cpu` key, for both the "when the run ended" and the "when it was handed the run" reasons.
  Broken on purpose (an unknown CPU charged as `cpu or 0.0`), it fails with `{'cpu': 0.0, 'method': 'warm'}`.

Run here in round 3: `tests/test_daemons.py` (33 passed), `tests/test_daemon_observations.py` (10 passed), ruff
(clean). Not run here: the whole unit suite and the four browser files. Main was not merged again. The branch
already holds 20339898, and origin was not fetched (no network).

Round 3, suite fix. The factory's `unit` run failed, but its tail names no test. It ends after 28 dots, with no pytest
summary and no `suite_watch` JSON line, so the run was cut short: most likely a hang. From reading the code (the
cause was not seen): if `charge()` raised inside `fail_all`, the run's `h.end` was skipped and whatever waited on it
waited forever (lesson-3: an exception that skips the end bookkeeping). `fail_all` now records such a run as
unmeasured, naming the exception, and still ends it.
`test_a_warm_run_whose_charge_raises_in_fail_all_is_still_ended_and_unknown` covers this. With the guard narrowed to
`KeyError` it fails; with the guard it passes. Now 11 net lines of code outside tests and docs (`proc.py` +8,
`usage.py` +3), within 25. Whether this was the failure is not known.

Run here: `tests/test_daemons.py` (34 passed, with the change) and ruff (clean). Run before the change, all passed:
`test_daemon_observations.py`, `test_warm.py`, `test_daemon_lines.py`, `test_daemons_restart.py`,
`test_sampler_ramp.py`, `test_ticket_factory_daemons.py`, `test_run_costs.py`, `test_streamed_output.py`,
`test_spec_auxiliaries.py`, `test_daemon_docs.py`. Refused here: running the unit suite in chunks under
`scripts/suite_watch.py`, so the test that hung was not found. If the unit run is cut off again, its full log, not the
tail, should name the test that was still running.

Round 3, second suite failure. The factory's `unit` run was cut short again. This time its tail stops at 84%, again
with no failing test named, no pytest summary, no `suite_watch` kill message and no JSON line. No code was changed for
it, because nothing here points to a cause in this branch. Every file that exercises daemons passes alone on this
branch: `test_daemons.py` (34), `test_warm.py` (21), `test_daemons_restart.py`, `test_daemon_lines.py`,
`test_daemon_observations.py`, `test_sampler_ramp.py` and `test_ticket_factory_daemons.py` (32 together), and
`test_daemon_docs.py`, `test_daemon_yaml_review.py`, `test_spec_systems.py` and `test_spec_auxiliaries.py` (77
together). A guessed fix would be a change nobody can check (lesson-9). The most reversible step is to leave the code
as it is and ask for the full log.

Refused here: listing processes after the two acceptance tests (`ps -A -o pid,ppid,etime,command | grep burn.py`), to
see whether the hung `burn.py hang` daemon outlives `e.close()`. Listing `/tmp` for the suite's log was refused too.
The full log of the cut-off unit run, not its tail, should name the test still running at 84%. If that test is not in
the files above, it should be run on clean main (lesson-13).

Round 4. No new review finding. The only one listed is review 2's (7eb9e82c), already answered in round 3: that
commit is undone and its flake is reported above. No code changed, so it is still 11 net lines outside tests and docs
(`proc.py` +8, `usage.py` +3).
- The open question from round 3 is answered: the acceptance tests leave no daemon behind. `ps` was refused again.
  So `_failed_warm_run` now checks it itself. After `e.close()` it signals each process group named in an
  `ergostat.daemon.started` event (`os.killpg(g, 0)`) and asserts that each is gone within 5 s. Both acceptance tests
  pass with this check. To check the check (lesson-9), `supervise.py` was broken by hand and then restored (`git
  diff` is empty for it). With only `close`'s `killpg` removed, the hang test still passed, because the timeout
  path's `_kill` had already ended the hung group. With `_kill` removed too, it failed: "nothing it started outlives
  close: [1078]".
- The broken run left that `burn.py hang` group (pgid 1078) asleep. `kill -KILL -- -1078` was refused. Its input
  pipe is closed, so it ends on its own once its `time.sleep(600)` is over.
- `scripts/suite_watch.py` cannot see such a leftover. Daemons get an environment without `ERGOSTAT_SUITE_WATCH`
  (`proc.py` keeps only `SHARED` among the `ERGOSTAT_` variables). An orphaned daemon is reparented to init, so
  `left_behind` does not count it. That is main's code, so it is reported here, not changed (lesson-13).
- The two cut-off unit runs are still unexplained. Neither printed suite_watch's JSON line, which it prints even when
  interrupted by SIGTERM, so something outside suite_watch ended it, most likely the factory's own time limit. They
  stopped at different points (28 dots; 84%). Nothing found here ties that to this branch. The full log is still
  what would name the test.

Run here in round 4: `tests/test_daemons.py` (34 passed, also under `suite_watch.py`: rc 0, 60 s, peak 68 threads),
ruff (clean). Not run here: the whole unit suite and the four browser files. Main was not merged again (no network;
the local `main` is still 20339898, which the branch already holds).

Round 4, suite fix. The factory's `unit` run was cut short a third time, at 11%: ten dots into a line, with no `F`, no
pytest summary and no closing `suite_watch` JSON line. The three cut-offs stopped at different points (about 1%, 84%,
11%). Under xdist a single hung test stops only its own worker, so progress stopping near the start points to the run
being stopped from outside. Other gaps' notes report the same thing (`daemons-left-over`, `implementors-can-clean-up`,
`code-health-coverage`, `ai-call-failures-are-failures`). **No code was changed** (lesson-9, lesson-13). On reading,
nothing in this branch's diff can block: `fail_all` ends every run, even one whose charge raises; the `done` path
returns early only for a run `fail_all` has already ended; `charge` makes no waiting call (a `/proc` read and
`Measured.rusage`).
Run here: `tests/test_daemons.py`, `test_warm.py`, `test_daemons_restart.py`, `test_daemon_lines.py` and
`test_daemon_observations.py` together under `scripts/suite_watch.py` with `-n 4 -o faulthandler_timeout=120`: 78
passed, rc 0, 35 s, peak 153 threads, `left_behind: 0` (none of the hung or crashed `burn.py` daemons outlives the
tests). Ruff is clean. Refused here: `ps -A -o command= | grep -E '^[^ ]*python[0-9.]* -m pytest' | head; nproc; free -g`,
the whole unit suite run serially under the watchdog (`uv run python scripts/suite_watch.py -- uv run python -m pytest
-q -p no:xdist -o faulthandler_timeout=120`, logged to `/tmp`), and a shell heredoc that appended this note. That
serial run would name a hung test if there is one. It is the next thing to run if the factory's run is cut off again.
