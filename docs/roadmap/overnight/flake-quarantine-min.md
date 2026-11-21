# flake-quarantine-min: A quarantined test never reds the queue

depends-on: []

Replaces the parked `flake-quarantine`, which grew too large and hit the kill rule, partly on counting a skip as a pass. The owner: "we can disable the flakey tests, or run them without blocking and review them after."

## Definition of done
- `tests/quarantine.txt` lists each test with who, when and why. It starts with `tests/test_leases.py::test_leases_survive_a_restart_the_fold_is_the_truth` and `tests/test_reload_in_place.py::test_a_removed_blocks_run_still_takes_messages_while_it_goes`.
- The queue, triage and implementor suites deselect those tests, then run them beside the suite without blocking, recording each result on its flake item from the whole log.
- A skip is never recorded as a pass. No automatic quarantine or release in this gap.

## Files to touch
`dev/bin/fac.py`, `dev/bin/queue.py`, `dev/bin/triage.py`, `tests/quarantine.txt`, `tests/test_factory.py`.

## Risks
- lesson-3: a run that could not be read is unknown, never a pass.

## Acceptance tests
- `tests/test_factory.py::test_a_quarantined_test_does_not_block_the_queue`
- `tests/test_factory.py::test_a_skipped_quarantined_test_is_not_a_pass`
- `tests/test_factory.py::test_a_quarantined_failure_is_recorded`

## Size budget
80 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Round 1: built; nothing of the definition is left. Choices made alone (each the most reversible):

- **`dev/bin/agents.py` touched too** (4 lines), though it is not in "Files to touch": the implementor's fast suites
  are made there (`agents.suites`), not in `fac.suite`, so this is the only place "the implementor suites deselect
  those tests, then run them beside the suite" can happen. `dev/README.md` gains a paragraph, *The quarantine*.
- **The list is read from the tree under test** (`<tree>/tests/quarantine.txt`: the queue's merged main, triage's
  worktree, the implementor's work). So a branch that adds a line quarantines that test in its own runs, and the diff
  shows it to the reviewer. No list means nothing is quarantined, and every test blocks.
- **Beside means after**: the quarantined tests run once after each unit run (the queue: after unit and browser,
  whatever they said; each bisecting run too), as `[suites] alone` with `-rA` (triage: `rerun`). Nothing runs at
  the same time as the suites, so the queue adds no load, only one more pytest start-up a run.
- **The result** (`flake.measured` on `flake/<test>`: `quarantined`, `last_run`, `last_run_at`, `last_run_log`):
  `pass` only on the test's own PASSED line with no FAILED or ERROR line, and `fail` on either. Anything else is
  `unknown`: skipped, not collected, a killed run, or one that raised before it wrote its log (lesson-3). A
  quarantined test's flake item is made in the kind's first state, `seen`. `ergostat.yaml` is unchanged.
- **Triage**: quarantined tests are taken off the rerun list (an old queue failure could still name them). When only
  quarantined tests failed, the gap is retried as a flake rather than blamed, because by definition those tests do
  not block.
- **Not done (out of scope)**: no automatic quarantine or release, no counts of runs per result (each result is its own
  event in the record), and no answer to the parked branch's triage-skip-count finding.
- **origin/main**: this clone has no `origin/main` ref and no network. The branch is on `main` 24756e50 (its base),
  so no other merge could be made or run.

Round 2: every finding of review/flake-quarantine-min-1 answered; nothing of the definition is left.

- **Blocking: the list is read from main, not the tree under test** (replaces round 1's second choice above).
  `fac.quarantine(repo, ref)` reads `git show <ref>:tests/quarantine.txt`: the queue's and triage's `pre` (main before
  the batch's merges; each bisecting run too), and for the implementor the drop's main (`live/drop.git`, the base its
  work was cloned from). A branch's own line quarantines nothing until it is on main, and a branch that deletes a line
  releases nothing in its own run. No list at the ref, or a ref that cannot be read, means none: every test blocks
  (lesson-3, failing closed). Test: `test_a_branch_cannot_quarantine_its_own_failing_test`, where a branch adds its
  own failing test to the list and the queue still records `gap.queue-failed` naming it. With the queue reading
  `HEAD` instead of `pre`, that test fails (checked).
- **Triage, only quarantined tests failed**: no `flake.seen`, and `gap.retried` with `retries: 0` (a sum, so no retry
  of `RETRIES` is spent). The gap goes back to the queue. The result of the run beside the suite is still recorded.
  Asserted in `test_a_quarantined_failure_is_recorded`; with `retries=1` restored, that test fails (checked). With
  main's list this case needs the list to change between a queue run and its triage, so it is rare.
- **lesson-5, a stale `quarantined: true`**: each run beside a suite first marks `quarantined: false` on every flake
  item still marked quarantined whose test is not on main's list. If the record cannot be read, the marks stay as
  they were and the suite goes on. Asserted in the new test; with the release removed, that test fails (checked).
- **Scope (non-blocking)**: `dev/bin/agents.py` (now 5 lines) and `dev/README.md` stay outside "Files to touch",
  for round 1's reasons. The README paragraph now says where the list is read from, and that a release is a change
  to main's list.
- Not distinguished by a test: the implementor reading the drop's main rather than its work. In the test factory both
  hold the same list, because the work is cloned from main. Net code outside tests and docs: 74 lines (budget 80).
- **origin/main**: still no `origin/main` ref and no network here. The branch was last merged with main 31cffd8f.
- **After round 2, the fast `unit` suite failed** with no pytest output in its tail (killed before pytest flushed:
  `suite_watch` always prints a last JSON line, and there was none). Not reproduced here: running the whole suite
  was refused in this session. The one change that reached the unit run was the two quarantined tests running again,
  since main has no list yet and round 2 reads only main's. Round 1, which deselected them, passed. Fix (the most
  reversible one): the implementor's fast suites also deselect the work's own lines (`agents.suites`: main's list
  run beside, plus the work's lines at `HEAD`, deselected and not run). That run lands nothing; the queue and triage
  still read only `pre`, so a branch that quarantines its own test is still red there.
  `test_a_branch_cannot_quarantine_its_own_failing_test` now asserts both; with the work's lines dropped, it fails
  (checked). Until this branch is on main, the queue run for this branch itself still runs the two tests, blocking.
- **After fd6bf38e, `unit` failed the same way again**: the tail stops at 80% partway through a line, with no FAILED
  line, no pytest summary and no `suite_watch` JSON line. So the whole container was stopped from outside the
  run (not by a test failing, and not by the watchdog, which always prints its line). Both quarantined tests were
  deselected in that run, so this time they are not the cause. No cause was found in this branch, and no code was
  changed for it. Run here one file at a time, everything passes: `tests/test_factory.py` (63 passed, 2 skipped),
  `tests/test_leases.py` (29), `tests/test_reload_in_place.py` (11), `tests/test_factory_knowledge.py` with
  `tests/test_factory_manager.py` (70), and `tests/test_modelreview.py` with `tests/test_redesign.py` (40, both new
  from main's merge 31cffd8f). None of the code this branch adds kills processes or containers (`fac.beside` only
  calls `fac.suite`, which kills only its own process group). Not run: the whole unit suite (forbidden to the
  implementor), and the docker exit code and resource readings of that run, which are not visible from here.
  Most likely an outside stop: the suite container's 12 GB memory limit, which also counts its 2 GB `/tmp` tmpfs,
  or the resource sampler. The next step is to read that run's `gap.*` resources and exit code, and to run the
  unit suite again on a quiet machine (lesson-10). Per lesson-13 this is reported, not fixed here.

Round 3: main a1d1b941 merged (0433a64c), with conflicts in `dev/bin/queue.py` and `dev/bin/triage.py` resolved so
that both sides' changes are kept.

- **queue.py `suites`**: main's coverage run (`[suites] queue_coverage`, `pre="HEAD"` default) plus the branch's
  quarantine read at `pre`. The coverage run passes its own `command`, which `fac.suite` does not deselect, so that
  command is put through `fac.deselected` with main's list. Without this, a traced unit run would block on the
  quarantined tests. No test covers that case yet (the coverage tests do not quarantine anything).
- **triage.py**: main's change is kept, so the rerun no longer holds the queue's lock (only `fac.wait_quiet`). The
  branch's rule is kept too: when only quarantined tests failed, there is no `flake.seen` and no retry is spent.
- Round 2's review findings were not reopened in this round. The brief listed only the conflicts. Still open from
  review/flake-quarantine-min-2: a ref that cannot be read releases every mark in `beside`; triage's release at an
  older `pre` can flip-flop the marks; and the implementor's own lines are deselected and never run.
- Run: `tests/test_factory.py` (74 passed, 2 skipped), `tests/test_code_health_coverage.py` (11 passed), ruff clean.
  Not run: the whole unit suite and the four browser files (the factory runs them).
