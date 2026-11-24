# cleanup-starts-before-the-gate: disk cleanup runs before builders are stopped, and survives a vanished folder

Seen 2026-11-24: `cleanup-when` only fired when `disk-free-enough` was off, which is the same 20 GB gate that stops new builds, so builders stopped every time before cleanup began; and `dev/bin/cleanup.py` aborted with FileNotFoundError when a folder vanished between listing and removal, freeing only part of what it found. The coordinator patched both live.

Change.
1. `cleanup-when` also fires while free disk is under a margin above the gate (start: 30 GB), as a model parameter.
2. `cleanup.py` skips a folder that is gone by the time it is removed, and finishes the rest.
Definition of done.
1. Tests: cleanup fires at 29 GB with the gate still held; a folder removed mid-run is skipped and the rest are removed.
2. Do not measure or change the live instance in the session.

## Where it stopped

Built, round 1. The live instance was neither measured nor changed.

- Margin (`dev/model/resources.yaml`): a goal `disk-free-for-cleanup` on `disk-free`, hold `>= 30`, read only by
  `cleanup-when` (`max(folders, margin, disk)`). The definition says "a model parameter", but an expr block's inputs
  can only read stocks, flows, auxiliaries, goals and blocks; ergostat's `parameters:` exist only for equations, which
  the engine doesn't evaluate live. A literal `30` in the expr would not be declared anywhere. The setpoint goal is the
  closest declared, changeable number and the most reversible choice (delete the goal and the input to undo it), and
  the file's header already says resource setpoints live there. Note: the live gate is 25 GB in the model (the
  definition says 20); the 30 GB margin is above either.
- `dev/bin/cleanup.py` `remove` returns False when the folder is gone (rmtree finds no top folder; for an install,
  git refuses and the folder no longer exists); a file in it that vanishes mid-rmtree is passed over; any other
  failure still raises. `main` prints "gone already: skipped", goes on with the rest, leaves vanished folders out of
  the folder count and out of the early count. The GB figure stays as `du` measured before removal, and the summary
  says so.
- Tests: `tests/test_factory_resources.py::test_cleanup_fires_at_29_gb_with_the_gate_still_held`,
  `tests/test_cleanup_vanished.py` (both tests). Each was seen to fail with its code broken: the margin input dropped
  from the expr, the FileNotFoundError catch removed, and every FileNotFoundError re-raised in the rmtree handler.
- Size: about 30 net lines outside tests and docs.
