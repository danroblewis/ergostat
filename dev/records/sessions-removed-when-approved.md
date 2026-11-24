# sessions-removed-when-approved: A finished gap's session folders are removed as soon as it is approved

The owner: "the work is in the git branch already, the work tree can be removed as soon as the work is Approved". Session folders are kept for `session_keep_hours` whatever their gap's state, and filled the disk until builders stopped.

Change. `dev/bin/cleanup.py` also removes a session folder whose gap is approved, queued, push-pending, merged or closed, unless it was touched in the last ten minutes or a running container mounts it. Removal stays by allowlist (only folders the factory named). The coordinator applied this live on 2026-11-23 (`finished_sessions`); land it properly, with tests.

Definition of done.
1. Tests: a folder of an approved gap is removed; one of a gap in fix or building is kept; one touched within ten minutes is kept; one a running container mounts is kept; an unreadable record removes nothing early.
2. The disk measure shows the change: the folders removed early are counted.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.
