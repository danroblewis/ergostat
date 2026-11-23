# cleanup-removes-every-role: the disk cleanup removes session folders of every role

depends-on: []

`dev/bin/cleanup.py:27-28` match session folders with `[a-z0-9-]*`, which has no underscore, so the folders of the roles `pipeline_manager`, `plan_reviewer` and `join_judge` (`<branch>-<role>-<stamp>-<hex>` and `<item>-<role>-<n>-claude-<hex>`) were never removed: on 2026-11-22, 438 folders and about 10 GB, while the disk sat at its 25 GB floor and held the builders back. The coordinator widened the patterns in the live instance.

## Definition of done
1. Both patterns accept underscores in the role (`[a-z0-9_-]*`), and nothing else changes in what they match.
2. A test makes a folder for each role in `dev/bin/agents.py` `TIMEOUTS` (both shapes, past the keep) and checks the cleanup removes every one and keeps a young one.

## Files to touch
`dev/bin/cleanup.py`, its test.

## Size budget
2 net lines of code outside `tests/` and `docs/`.
