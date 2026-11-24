# sessions-removed-when-approved: A finished gap's session folders are removed as soon as it is approved

The owner: "the work is in the git branch already, the work tree can be removed as soon as the work is Approved". Session folders are kept for `session_keep_hours` whatever their gap's state, and filled the disk until builders stopped.

Change. `dev/bin/cleanup.py` also removes a session folder whose gap is approved, queued, push-pending, merged or closed, unless it was touched in the last ten minutes or a running container mounts it. Removal stays by allowlist (only folders the factory named). The coordinator applied this live on 2026-11-23 (`finished_sessions`); land it properly, with tests.

Definition of done.
1. Tests: a folder of an approved gap is removed; one of a gap in fix or building is kept; one touched within ten minutes is kept; one a running container mounts is kept; an unreadable record removes nothing early.
2. The disk measure shows the change: the folders removed early are counted.

Boundary (the owner, 2026-11-23). Anything general goes in ergostat's core as options a model declares, off unless declared, naming no gaps, software or factories. This factory is the first user and its choices live in its own model. Do not measure or change the live instance in the session: the coordinator applies changes.

## Where it stopped

Round 1: built. Nothing in `ergostat/` changed (the cleanup is the factory's own program); about 117 net lines in
`dev/bin/` (`cleanup.py` +112, `resources.py` +3), within the 600 budget.

What it does (`dev/bin/cleanup.py`):
- `finished(cfg, found)`: of the session folders the factory named (the same `SESSION`/`CLAUDE` allowlist as before,
  under `<live>/sessions/` only), those that every gap whose name the folder begins with is in a state of
  `[resources] finished_states`. A gap's names are its branch (`fac.branch_of`, agents.clone's) and its id's slug cut to
  64 (sessions.py's, for Claude Code's folders). A folder whose name begins with several gaps' names (a finished `foo`
  and a building `foo-more`), or a branch a later gap `continues` while building, is kept: every owner must be
  finished. A folder no gap's name begins (research, backlog, a review's librarian) is never removed early.
- Kept also when touched in the last ten minutes (`QUIET`: the folder, the entries in it and in its folders, and its
  clone's `.git`; unreadable counts as now), or when a running container mounts it, a folder in it or one holding it
  (`docker ps -q`, then `docker inspect` of their mounts).
- Fails closed: the record unread, Docker not answering (or a container gone between the two asks), or a
  `finished_states` that is not a list of strings: nothing is removed early this pass, said on stderr; removal by age
  goes on as before. `finished_states` unset or `[]`: never early (off unless declared).
- Read-decide-write (lesson-1): no lock is shared with the session starters, so `main` re-reads each chosen folder's
  touch time just before removing it and keeps one touched since. A new session always makes a new folder (a fresh
  name), so a gap reopened after the record was read loses only an old clone of work already on its branch.
- The measure (done item 2): each pass adds its early removals to `run/resources/cleanup.json` (`early`, `early-gb`,
  `early-total`, `since`) under its lock; `cleanup.sizes` gives `sessions-removed-early` (the running total; None when
  that file cannot be read, 0 before any), a slow reading of `resources.py` and shown in `resources.py line`. The pass
  prints `N folders, X GB (K of finished gaps, Y GB, early)`.
- The factory's choice is in its own config: `dev/factory.toml` `[resources] finished_states = ["approved", "queued",
  "push-pending", "merged", "closed"]`. Decision taken alone (the reversible option): the states are a setting, the ten
  minutes a constant as the definition fixes it; no auxiliary was added to `dev/model/resources.yaml` for the new
  reading (only the disk-cleanup block's description changed), so the live model's sensors are unchanged until the
  coordinator chooses to declare one.

Tests (`tests/test_cleanup_finished.py`, 8 passed): an approved, queued, push-pending or merged gap's folders (both
shapes, a branch cut to 32) removed; a gap in fix or building, a name shared with a building gap, a continued branch
and a non-gap name kept; touched five minutes ago, or only its clone's index written now, kept; a container mounting the
clone, the folder or the sessions folder keeps it; the record, Docker or the setting unreadable, or the setting unset,
removes nothing early while an aged folder is still removed; a folder touched after it was chosen is kept and not
counted; the count runs on across passes and an unreadable count reads None. Seen to fail (lesson-9): the state
ignored, the quiet check removed from `finished` (this needed the direct `finished` assertion: `main`'s re-check hid
it), `touched` reading only the folder, and the mount check removed with Docker errors swallowed each failed a test.
Not seen to fail: an unreadable record has no fail-open variant to try (no gap read means no name matches).

Not run here: the whole unit suite and the four browser files (no page changed). `dev/bin/plan.py` and
`dev/bin/review.py` have ruff findings on main that this branch does not touch.

## Entry

section: The factory (ergostat on ergostat)
done: 2026-11-24 A finished gap's session folders are removed by the disk cleanup as soon as it is approved.

- **A finished gap's session folders are removed as soon as it is approved** (done, on
  `sessions-removed-when-approved`): `dev/bin/cleanup.py` removes a session folder once every gap whose name it begins
  with is in `[resources] finished_states` (approved, queued, push-pending, merged, closed), unless touched in the last
  ten minutes or mounted by a running container; an unreadable record, Docker or setting removes none early. Counted
  as the reading `sessions-removed-early` (`run/resources/cleanup.json`).
