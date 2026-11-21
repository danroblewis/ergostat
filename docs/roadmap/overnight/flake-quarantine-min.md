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
