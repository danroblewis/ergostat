# library-fetch: libraries fetched by git URL, pinned in a lock

Built on `factory/library-fetch`; its definition of done is `dev/records/library-fetch.md`.

A model's main file may name up to 16 libraries under `libraries:`, each a git repository (https or file) at a tag,
branch or commit, optionally a folder of it. `ergostat library fetch` clones each into `.libraries/NAME/` and pins it
in `libraries.lock` by commit and tree hash; every load checks the copy against the lock and reads the templates from
the bytes it hashed. A library marked `trust: owner` can be used; any other is listed but not expanded until the
provenance gate and the sandbox reach fetched libraries.

- How it works and the error codes: SPEC §2a, *Libraries fetched by git URL*.
- What it defends against, and what it does not: SECURITY, *Libraries you did not write*.
- Where it sits among the shared-libraries work: GAPS, *Shared libraries*.

The code: `ergostat/library/sources.py` (the allowlists), `tree.py` (extract and hash), `fetch.py` (git, the lock),
`fetched.py` (load), `ergostat/cli/library.py`, and `files.tree` in `ergostat/spec/files.py` (the one walker, kept
in the last good model's snapshot as `trees`). The tests: `tests/test_library_fetch.py`.
