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

## Where it stopped

Round 1: built. `ergostat/library/fetch.py` is 217 lines. All six acceptance tests pass: 13 cases, because the kill test is parametrized over clone/archive × stall/size × with/without `os.waitid`. ruff is clean. `main` has not moved since the clone, so there was nothing to merge.

The parked branch `factory/library-fetch` is not in this clone, so the module was written fresh to this definition. The choices made, each the more reversible one:
- `fetch.fetch(root, libraries, update=False, say=print)` returns name → `fetched` or `kept`. It raises `FetchError(code, name)` with code `bad-lock`, `linked-library-folder`, `bad-version`, `git-failed`, `git-limit` or `lock-mismatch`. `TreeError` and `SourceError` from library-fetch-tree pass through. The first refusal stops the fetch. Libraries fetched before it keep their copy and lock entry. The acceptance tests' `--update` is the `update=True` argument. The CLI flag belongs to library-fetch-load.
- `libraries.lock` sits beside `.libraries` in `root`. It is JSON: name → `{git, version, path?, commit, tree}`, where `tree` is `tree.digest` of the copy. It is written whole after each library's swap, by `os.replace` from a `mkstemp` file. `.flock` is never replaced. The lock is read again for each library inside the flock. Entries for libraries no longer listed are kept, not pruned.
- Each library is a bare `git clone` of the whole repository. Then `rev-parse --verify VERSION^{commit}` resolves the version, so a branch, a tag or a commit all work. Then `git archive COMMIT[:PATH]` writes to a file in the temporary folder, which `tree.extract` reads into `copy`. So the size poll and `RLIMIT_FSIZE` cover the archive too, and the extract needs no thread. `check-ref-format --allow-onelevel` runs through the same limited runner. `GIT_ALLOW_PROTOCOL=https:file` overrides any `protocol.*` config. `http.followRedirects=false`, an empty `credential.helper`, `core.sshCommand=false` and `--template=` are added to `SAFE`.
- Without `update`, an entry whose source matches the lock and whose copy exists is kept with no git run, and its copy is not hashed again. If the copy is missing, it is fetched again, and a commit or tree other than the locked one is `lock-mismatch`. A non-hex locked commit is `bad-lock` before any git runs. With `update`, the version is resolved again and the entry moves.
- The group kill happens while the leader is not yet reaped. A `waitid(WNOWAIT)` peek keeps the group id from being reused (lesson-11). Where `os.waitid` is missing, `poll()` reaps the leader, and the group is killed only while the leader is still alive. In that case a child left running after a normal exit of the leader is not killed. That is the one gap in the fallback.
- Checked by breaking the code (lesson-9). Each break was seen to fail its test: killing only the leader (all 8 kill cases fail), no flock (lock test), no restore on a failed lock write, no link check on `.libraries/NAME`, and no hex check on the locked commit.
- SPEC and the agent guide are unchanged: a user can reach none of this until library-fetch-load adds the CLI and the load step.

Left: nothing in this definition. library-fetch-load builds on it.
