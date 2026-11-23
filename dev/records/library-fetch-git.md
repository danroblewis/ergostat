# library-fetch-git: a library fetched by git URL into `.libraries/NAME`, pinned by commit and tree in `libraries.lock`
depends-on: [library-fetch-tree]

## Definition of done
This takes over `factory/library-fetch`'s `ergostat/library/fetch.py`, trimmed to fit.
- Git runs with `sandbox/git.py`'s env and `SAFE` options, `GIT_ALLOW_PROTOCOL=https:file`, no redirects, no credential helper and no ssh, and `--end-of-options` before the URL and ref. A ref also passes `git check-ref-format` after the Python check. Each git process gets its own session, a 100 MB `RLIMIT_FSIZE`, a poll of the folder size and a 120 s limit. A process past a limit has its whole process group killed, `git archive` included. This works where `os.waitid` is missing.
- An exclusive flock on `.libraries/.flock` is held across reading the lock, cloning and extracting into `mkdtemp`, the swap, and writing the lock. `.libraries` and `.libraries/NAME` must not be symlinks, and `.flock` is opened with `O_NOFOLLOW`. An unreadable lock stops the fetch. An entry is re-resolved when `git`, `version` or `path` changes. A locked commit that is not hex never reaches git. If a re-fetch's commit or tree differs from the lock, it is refused.
- Fetch never extracts over an existing copy. A failed lock write puts the old copy back. Fetch deletes only its own temporary folder, and only after checking the folder resolves under `.libraries`.

## Relation to other work
- library-fetch-tree: waits for it and uses its extract and digest functions.
- library-fetch-load: adds the CLI and the load step on top of this.

## Files to touch
- `ergostat/library/fetch.py` (new)
- `tests/test_library_fetch_git.py` (new)

## Risks
- lesson-1: the read-lock / clone / write-lock sequence must stay under one flock, and the flock file must never be replaced.
- lesson-6: a stalled or oversized git must have its group killed, not just abandoned.
- lesson-11: every rename and rmtree is on a path built from NAME, so it must be checked to resolve under `.libraries`.

## Acceptance tests
- `tests/test_library_fetch_git.py::test_fetch_writes_lock`: a `file://` repo at a tag yields a copy and a lock entry `{git, version, path, commit, tree}`.
- `tests/test_library_fetch_git.py::test_lock_held_across_write`: a second fetch, started in a subprocess while the first is held between extract and lock write, prints `waiting for the libraries lock`. At the end, both entries are in the lock.
- `tests/test_library_fetch_git.py::test_update_drops_deleted_files`: `--update` after an upstream delete, with a planted stray file, leaves neither file behind.
- `tests/test_library_fetch_git.py::test_failed_lock_write_keeps_old`: the old copy and the old lock entry are intact after the lock write fails.
- `tests/test_library_fetch_git.py::test_stalled_and_large_git_killed`: the timeout and size ceiling, patched small, leave no group alive and no `.tmp-` folder. This also holds with `os.waitid` removed.
- `tests/test_library_fetch_git.py::test_linked_library_folder_refused`: a symlinked `.libraries` or `.libraries/NAME` is refused, and its target is untouched.

## Size budget
240 net lines
size: L (confidence: medium)
