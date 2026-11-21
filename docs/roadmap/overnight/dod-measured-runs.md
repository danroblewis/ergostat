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
