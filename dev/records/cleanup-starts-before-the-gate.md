# cleanup-starts-before-the-gate: disk cleanup runs before builders are stopped, and survives a vanished folder

Seen 2026-11-24: `cleanup-when` only fired when `disk-free-enough` was off, which is the same 20 GB gate that stops new builds, so builders stopped every time before cleanup began; and `dev/bin/cleanup.py` aborted with FileNotFoundError when a folder vanished between listing and removal, freeing only part of what it found. The coordinator patched both live.

Change.
1. `cleanup-when` also fires while free disk is under a margin above the gate (start: 30 GB), as a model parameter.
2. `cleanup.py` skips a folder that is gone by the time it is removed, and finishes the rest.
Definition of done.
1. Tests: cleanup fires at 29 GB with the gate still held; a folder removed mid-run is skipped and the rest are removed.
2. Do not measure or change the live instance in the session.
