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
