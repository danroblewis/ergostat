# library-fetch: libraries fetched by git URL into `.libraries/NAME/`, pinned by commit and content hash in `libraries.lock`, checked every time the model loads
depends-on: []

## Definition of done

**Config.** The main file (and only the main file) can hold `libraries:`, a map with at most 16 entries. More than 16 is error `too-many-libraries`. `libraries:` in an include is error `libraries-in-include`. Each entry is keyed by NAME and has:
- `git:` (required);
- `version:` (required): a tag, a branch or a commit sha;
- `path:` (optional): a subfolder of the repository;
- `trust:` (optional): only the value `owner`.

`ergostat/library/sources.py` checks every entry. Load runs the check and so does `fetch`, again, before any git process starts. Anything refused is error `bad-library-source`, and the message names the field. Every rule is an allowlist; none is a denylist or a prefix match:
- **NAME** matches `^[a-z][a-z0-9-]{0,63}$`.
- **`git:`** is parsed with `urllib.parse.urlsplit`. It is accepted only as one of:
  - `https://HOST[:PORT]/PATH`: HOST matches `^[A-Za-z0-9][A-Za-z0-9.-]*$`, PORT is digits only, and PATH is built from `[A-Za-z0-9._~/-]` with no `..` segment;
  - `file:///ABSOLUTE/PATH` with the same PATH rule.

  There can be no userinfo, no query and no fragment. Every other scheme is refused: `ssh`, `http`, `ext::` and the scp-like `host:path`.
- **`version:`** is either 40 or 64 lowercase hex characters, or a ref name that:
  - uses only `[A-Za-z0-9._/-]`, is at most 200 characters and does not start with `-`;
  - contains no `..`, `//` or `@{`;
  - has no leading or trailing `/` or `.`, and does not end in `.lock`.

  Load cannot run processes, so it checks this in Python. `fetch` also runs `git check-ref-format --allow-onelevel REF`, and only after REF has passed the Python check.
- **`path:`** is relative, uses only `[A-Za-z0-9._/-]` and has no `..` or empty segment.

**Running git.** Every git call in fetch:
- uses the environment and `-c` options from `ergostat/sandbox/git.py` (`ENV`, `SAFE`);
- adds `GIT_ALLOW_PROTOCOL=https:file`, `-c http.followRedirects=false`, `-c credential.helper=` and `-c core.sshCommand=false`;
- puts the URL and REF after `--end-of-options`, as in `git fetch --no-tags --depth 1 --end-of-options URL REF`.

**`ergostat library fetch [NAME...] [--update]`** (in `ergostat/cli/library.py`):
- It reads the main file live with the loader's own YAML reader and takes only `libraries:`. It never calls `open_project` or `goodmodel.fallback`. The topic `library` is not in `goodmodel.READS`.
- If the main file cannot be parsed, or `libraries:` fails the check, it stops with rc 2 and names the YAML error. It runs no git process and writes nothing.
- It takes an exclusive `flock` on `.libraries/.flock`. That file is created once and never replaced. If the lock is already held, fetch prints `waiting for the libraries lock` to stderr and then blocks.
- The lock is held across the whole read–decide–write:
  1. Read `libraries.lock`. A missing file counts as empty. Unreadable or invalid JSON stops the fetch (rc 2); it is never treated as empty.
  2. Decide, for each named entry (all entries if none are named):
     - Entry locked with the same `git`/`version`/`path`, the copy present and its tree hash matching: nothing to do, no network.
     - Same entry but the copy is missing or does not match: fetch the locked commit again.
     - `git`, `version` or `path` differs from the lock entry, or there is no lock entry: resolve `version` from scratch.
     - `--update`: resolve `version` from scratch for an unchanged entry too.
  3. Write.
- **Clone.** Each fetch works in a new folder made by `mkdtemp(prefix=".tmp-", dir=.libraries)`:
  1. `git init --bare` there.
  2. `git fetch --depth 1` of REF, or of the locked commit.
  3. If a fetch by sha is refused, a full fetch of `version`.
  4. `git rev-parse --verify` the commit, then `git archive --format=tar COMMIT [-- PATH]`.

  If a re-fetch's commit or tree hash differs from the lock, it is refused. The old copy stays.

  Each git process is started with `start_new_session=True` and `RLIMIT_FSIZE` = 100 MB. That cap is enforced by the kernel and limits any single file, including the pack. While it runs, a loop sums the temporary folder's sizes (lstat) every 0.25 s and kills the process group past 100 MB, or past 120 s. It then waits for the process. The docs say the total can overshoot by at most what arrives in one 0.25 s poll. Fetches run one after another, never in parallel.
- **Extract.** `git archive`'s output is streamed into `tarfile` mode `r|` by `tree.extract`, into `TMP/copy`:
  - Allowed members: directories, regular files (exec bit kept), and symlinks with a relative target that stays inside the copy.
  - Refused: hardlinks, devices, FIFOs, absolute names, `..`, and any member under a path that is a symlink member. Symlinks are created last.
  - Files are opened with `O_CREAT|O_EXCL|O_NOFOLLOW`.
  - Caps: 2,000 entries and 20 MB. The byte cap is checked twice: on the sum of the tar headers' declared sizes before a member is read, and on the bytes actually written, while they are written.
- **Swap and lock.** The tree hash is computed by `tree.read` on `TMP/copy`, the same function load uses. Still under the flock:
  1. The old `.libraries/NAME` is renamed to `TMP/old`.
  2. `TMP/copy` is renamed to `.libraries/NAME`.
  3. The lock entry `{git, version, path, commit, tree: "sha256:…"}` is written into the entries read in step 1, with only NAME's entry changed. The file is written to a temporary file and moved over `libraries.lock` with `os.replace`.
  4. `TMP` is removed.

  Fetch never extracts into an existing copy. On any failure `TMP` is removed and the old copy and lock entry stay as they were.
- **Deletion.** Fetch deletes only folders it made itself: the `mkdtemp` folder and `old` inside it. It checks that every path resolves under `<main dir>/.libraries`. If `.libraries` or `.libraries/NAME` is a symlink, fetch refuses (`lstat`).

**Load** (`ergostat/library/fetched.py`, called from `spec/load.py` whenever `libraries:` is present). For each entry it checks, in order. The first failure refuses the library:
1. `libraries.lock` is read through `files.read_text`.
   - Missing, or no entry for NAME, or an entry whose `git`/`version`/`path` differ from the config: `library-unlocked`.
   - Unparsable: `library-lock-unreadable`, and every library is refused.
   - An entry with no `tree` or `commit`: `library-unlocked`.
2. The copy is read by a new `files.tree(root, max_entries, max_bytes)`. Live, it:
   - walks with `os.lstat` and never follows a symlink;
   - refuses any entry that is not a regular file, a directory or a symlink (a FIFO, socket or device) without opening it;
   - opens files with `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` and checks `S_ISREG` with `fstat` before reading;
   - reads at most the bytes left under the cap plus one;
   - applies the same caps as fetch: 2,000 entries and 20 MB.

   It returns `{rel: (kind, bytes | target)}`. The file bytes are recorded in `Reads.files` and the listing in a new table, `Reads.trees`. `goodmodel.keep` stores `trees` in the manifest, and replay answers both tables from the snapshot. A missing copy is `library-missing`. An entry of the wrong kind, a copy over a cap, or a tree hash that is not the lock's is `library-altered`, with the reason.
3. Templates come only from that same dict, so the bytes hashed are the bytes parsed. `templates.read` gains `text=`. Template files are `*.yaml`, `*.yml` and `*/template.yaml` under the copy, and symlinks are never read. Each template gets `library=NAME` and `trusted = (trust == "owner")`.

Lookup order: the owner's `library:` folders and `$ERGOSTAT_LIBRARY` first, then fetched libraries in config order, then ergostat's own. Shadowing is noted as it is today.

**Uses.** A use of a template from a library without `trust: owner` is error `library-untrusted`. Such templates are found and listed, but never expanded. The trust gate by provenance and the sandbox are later gaps that will relax this. When a use names a missing template while any library is refused, the `unknown-template` message adds every refusal: `library NAME refused: <code>, <reason>`.

**Docs.**
- SPEC §2a: `libraries:`, the lock, `ergostat library fetch`, the error codes and the caps. It says the copy is checked when the model loads; a script the template runs from `${here}` is read again when it runs. It does not claim that what runs is what was locked.
- `docs/SECURITY.md`: the fetch threat model in one paragraph.
- `docs/GAPS.md`: the shared-libraries entry says fetch and lock are done, with the refusal of lock entries without a tree and the explicit hashing of symlinks.

## Files to touch

- New: `ergostat/library/sources.py`, `ergostat/library/tree.py`, `ergostat/library/fetch.py`, `ergostat/library/fetched.py`, `ergostat/cli/library.py`
- `ergostat/library/templates.py`, `ergostat/library/uses.py`, `ergostat/spec/load.py`, `ergostat/spec/files.py`, `ergostat/goodmodel.py`, `ergostat/cli/__init__.py`
- `docs/SPEC.md`, `docs/SECURITY.md`, `docs/GAPS.md`, `docs/roadmap/overnight/library-fetch.md`
- `tests/test_library_fetch.py`. Its repositories are local `file://` repos built with git in `tmp_path`.

## Risks

- **lesson-1.** If the flock is not held across read-lock → clone → swap → write-lock, two fetches lose each other's entries. Locking a file that is later replaced also makes the lock useless. At load, checking the hash and then re-reading the files from disk would use unverified bytes.
- **lesson-3.** A missing lock, a missing entry, a missing copy, an unreadable lock, an entry with no tree, or a refused library that quietly drops its templates: each must stop and be named, never count as empty.
- **lesson-4.** Without caps there is no bound on the number of libraries, the clone size, the clone time, the archive's entries and bytes (header sizes and bytes written), or the copy read at load.
- **lesson-5.** Extracting over an existing copy leaves deleted files behind. A changed `git:` must not reuse the old lock entry.
- **lesson-6.** A git process past the ceiling or the timeout must be dead (process group killed), not only abandoned.
- **lesson-7.** A new topic must not run on the read-only fallback. The `files.tree` table must survive replay.
- **lesson-8.** Claims are limited to these: URLs and refs pass an allowlist; the copy is verified at load; the clone overshoot is bounded by one poll. Scripts are not claimed to be verified at run time.
- **lesson-9.** See each test's "fails if".
- **lesson-10.** The concurrency test waits for a printed marker, never a sleep.
- **lesson-11.** Every rmtree and rename works on a path built from NAME.
- **lesson-12.** Every point of the previous plan review is answered above.
- **lesson-13.** A failure elsewhere is reported, not fixed.

## Acceptance tests

All in `tests/test_library_fetch.py`.

- **`test_fetch_locks_and_load_uses_it`**: fetching a tagged library writes `libraries.lock` with the commit and tree. A `use:` of its template with `trust: owner` loads, and `check` shows the template coming from the library.
- **`test_bad_name_and_scheme_refused`**: each of these is refused at config load and by `fetch`, with zero git calls (the runner is monkeypatched to record calls) and no file `x` created:
  - names `../x` and `Bad`;
  - URLs `ext::sh -c touch x`, `ssh://-oProxyCommand=touch x/r`, `https://u:p@h/r`, `http://h/r`, `https://-h/r`, `file://rel`, and one with `?q`;
  - versions `--upload-pack=touch x`, `-c`, `a..b`, `x@{1}` and `x.lock`;
  - path `../up`.

  It also checks that the argv built for git puts `--end-of-options` before URL and REF. Fails if any check is a prefix match or is missing.
- **`test_fetch_holds_lock_across_write`**: the step between extract and lock write is monkeypatched in an in-process `fetch a`. The patch starts `python -m ergostat library fetch b` in a subprocess, waits for `waiting for the libraries lock` on its stderr (up to 30 s), checks it is still running, then returns. Afterwards both `a` and `b` are in the lock, both copies exist, and the subprocess is killed in `finally`. Removing the flock makes it fail: the marker never appears and `b`'s entry is lost. The report must say this was tried.
- **`test_update_remake_drops_deleted_files`**: `version: main` is fetched. Upstream then deletes `b.yaml`, and the test plants `stray.yaml` in the copy. After `fetch --update`, neither file is in `.libraries/NAME/`, the commit and tree in the lock have changed, and load succeeds. Fails if fetch extracts into the existing folder.
- **`test_changed_git_alone_is_unlocked`**: changing only `git:` gives `library-unlocked`, and its template is unknown with that reason. Fails if the lock is matched by name only.
- **`test_missing_unlocked_and_treeless_refused`**, three cases:
  - copy deleted: `library-missing`;
  - lock file deleted, or entry removed: `library-unlocked`;
  - entry without `tree`: `library-unlocked`;
  - lock made invalid JSON: `library-lock-unreadable`.

  Each asserts the template is not available and that the `unknown-template` message carries the reason. Each fails if its check is removed, because the copy on disk would load.
- **`test_altered_copy_refused`**: changing one byte gives `library-altered`.
- **`test_untrusted_use_refused`**: without `trust: owner`, a use gives `library-untrusted` and no part is expanded.
- **`test_load_parses_the_bytes_it_hashed`**: `files.tree` is wrapped so that, after it returns, the test rewrites the template's `description` on disk. The loaded template has the original description. Fails if load re-reads from disk.
- **`test_fifo_in_copy_refused_without_hanging`**: an `os.mkfifo` in the copy, loaded in a subprocess with a 20 s timeout, gives `library-altered` (not a regular file). Fails, by hanging and timing out, if the walk opens it.
- **`test_symlink_hashed_not_followed`**: changing a symlink's target in the copy gives `library-altered`. An archive symlink escaping the copy, and a member under a symlink, are refused at fetch.
- **`test_caps_refuse_large`**: each part fails if its cap is removed.
  - Clone ceiling, patched to 1 MB, on a repo with a 3 MB random blob: refused. The git process group is gone (`os.killpg(pgid, 0)` raises), and no `.tmp-` folder, copy or lock entry is left.
  - Archive entries cap and bytes cap, patched small: refused.
  - The written-bytes check, with the declared-size helper monkeypatched to return 0: refused.
  - 17 `libraries:` entries: `too-many-libraries`.
  - At load, a copy over the cap (planted file, cap patched after fetch): refused, naming the cap rather than the hash.
- **`test_library_folder_link_refused`**: `.libraries` or `.libraries/NAME` as a symlink to another folder makes fetch refuse, and the target is untouched.
- **`test_fetch_refused_under_fallback`**: a good model is kept (with a library), then the YAML is made unparsable. `library fetch` exits rc 2 naming the YAML error, with no git call, `goodmodel.fallback` never called, and `.libraries` and the lock unchanged. `goodmodel.reads` is False for `library fetch` args. Fails if `library` is added to READS or fetch opens the project.
- **`test_fallback_reads_library_from_snapshot`**: the model is kept, then the copy is deleted and the YAML broken. `ergostat status` runs on the last good model with the library's parts. Fails if `trees` is not kept or replay walks the disk.
- The existing `tests/test_cli_fallback.py`, `tests/test_templates.py` and `tests/test_modelling_template.py` pass unchanged. All suites run again after merging origin/main.

## Size budget

560 net lines outside `tests/` and `docs/`. Rough split: sources 70, tree 110, fetch 170, fetched 70, CLI 60, and about 80 across templates, uses, load, files, goodmodel and cli/__init__.

## Notes from the plan review (answer each)

- Swap rollback: after step 1 (old renamed to TMP/old), any failure must rename TMP/old back to .libraries/NAME (moving the new copy aside first) before TMP is removed; as written, 'on any failure TMP is removed' deletes the old copy and makes the 'old copy and lock entry stay' claim false. Add a test that makes the lock write raise and asserts the old copy and the old lock entry are intact.
- All allowlist regexes (NAME, HOST, PATH chars, ref) must use re.fullmatch (or \Z), not re.match with '$', which accepts a trailing newline. Add 'a\n' as a NAME and 'main\n' as a version to test_bad_name_and_scheme_refused; load has no check-ref-format to catch it.
- Name one walker and one hash function shared by fetch and load (state whether tree.read wraps files.tree or the reverse), and give the hash a canonical, unambiguous encoding: sorted rel paths, kind tag, length-prefixed bytes or target.
- Hash the exec bit, e.g. kind 'file' vs 'exec', because extraction keeps it. A chmod +x on a copied file must give library-altered; add it to test_altered_copy_refused.
- lstat .libraries (refuse if it is a symlink) before creating or opening .libraries/.flock, and open the flock file with O_NOFOLLOW.
- git archive writes to a pipe, so neither RLIMIT_FSIZE nor the folder poll covers it. State that the 120 s timeout and the process-group kill also apply to git archive, and that a tarfile refusal kills the archive process group.
- The 120 s clone timeout has no test. Add one with the timeout patched small against a stalled source (e.g. a wrapper that blocks), asserting the process group is gone and TMP removed, or explain why it cannot be tested.
- test_missing_unlocked_and_treeless_refused says 'three cases' but lists four; fix the wording so each case is asserted.

## Where it stopped

Built, round 1. Every acceptance test above is in `tests/test_library_fetch.py`, with three more: 
`test_failed_lock_write_keeps_old_copy_and_entry` (review note 1), `test_stalled_git_is_killed_by_the_timeout` (note 7)
and `test_sources_are_whole_matches`. All 18 pass. `tests/test_cli_fallback.py`, `tests/test_templates.py`,
`tests/test_modelling_template.py`, the four `tests/test_library_*.py` files, `tests/test_spec_schema.py` and
`tests/test_spec_structure.py` pass unchanged. Ruff is clean. Local `main` has nothing this branch lacks (`git merge
main`: already up to date), so there was nothing new to merge or run again. Not run here: the whole unit suite, the
four browser files (no page changed) and `demo_check` (no example touched).

**Tests seen to fail with their guard removed (lesson 9).** Each mutant was applied, run, and reverted:
- flock removed: `test_fetch_holds_lock_across_write` fails because the marker never appears (`queue.Empty` after
  30 s). With the marker wait also taken out of the test, it fails on `{'a'} == {'a', 'b'}`: b's entry is lost.
- templates parsed from disk (`text=None`): `test_load_parses_the_bytes_it_hashed` fails.
- the lock matched without `git`: `test_changed_git_alone_is_unlocked` fails.
- the exec bit not hashed: `test_altered_copy_refused` fails.
- the written-bytes check removed: `test_caps_refuse_large` fails.
- `trees` not kept: both fallback tests fail (keep's read-back refuses the snapshot).
- the FIFO kind check and `O_NONBLOCK` removed: `test_fifo_in_copy_refused_without_hanging` times out at 20 s.
  With only the lstat kind check removed, `O_NONBLOCK` plus the `fstat` check still refuse it without hanging.
- `MAX = 17`, or NAME through `re.match(...$)`: `test_caps_refuse_large` or `test_bad_name_and_scheme_refused` fails.
- the link-escape check removed: `test_symlink_hashed_not_followed` fails.
- the leader killed but not its group: `test_stalled_git_is_killed_by_the_timeout` fails.
- no rollback of the old copy: `test_failed_lock_write_keeps_old_copy_and_entry` fails.
- the new copy written over the old folder: `test_update_remake_drops_deleted_files` fails.

**The plan review's notes, each answered.**
1. Swap rollback: if the lock write fails, the new copy goes back to `TMP/copy` and `TMP/old` comes back to
   `.libraries/NAME` before `TMP` is removed. Tested by `test_failed_lock_write_keeps_old_copy_and_entry`.
2. Every allowlist uses `re.fullmatch`. `a\n` and `main\n` are in the bad list, and so are `https://h/r\n`,
   `h:path`, `#f`, `file:///a/../b` and a float version.
3. One walker and one hash: `tree.read` wraps `files.tree`, and `tree.digest` hashes the result. Paths are sorted.
   Each entry is its kind, a NUL, then an 8-byte length and the path, then an 8-byte length and the bytes or link
   target.
4. The exec bit is hashed: the kind is `file` or `exec`. `chmod +x` is a case in `test_altered_copy_refused`.
5. `.libraries` is checked with lstat (a link is refused) before `.flock` is created or opened. `.flock` is opened
   with `O_NOFOLLOW`.
6. `git archive` gets a 120 s timer that kills its process group. Any refusal while reading its tar stream also kills
   the group. SPEC and SECURITY say so.
7. The timeout is tested. `fetch.argv` is patched so that the `fetch` call, then the `archive` call, runs
   `sh -c 'sleep 60 & sleep 60'` through the real `_start`. The test asserts every group is gone and no `.tmp-`
   folder, copy or lock is left.
8. The test's docstring names five cases (copy deleted, lock deleted, entry removed, entry without tree, invalid
   JSON), and each is asserted. The invalid-JSON case also checks that `fetch` stops with rc 2, runs no git and leaves
   the lock as it was.

**Choices taken where the definition was silent (each easy to reverse).**
- `libraries.lock` is `{"libraries": {NAME: {git, version, path, commit, tree}}}`. `path` is `""` when none is given.
- A refused library is an error, so the model does not run, and the error carries the refusal's code. A use is
  refused separately (`unknown-template` or `library-untrusted`).
- With `path:`, the archive's `PATH/` prefix is stripped, so `.libraries/NAME` holds that folder's contents.
- `git check-ref-format` and `git archive` take no `--end-of-options`. The ref has already passed the Python check
  (it cannot start with `-`), and the archive's commit is a sha that `rev-parse --verify` returned. I could not check
  whether `check-ref-format` accepts `--end-of-options`: the session refused running git directly. `fetch`,
  `rev-parse` and the URL do use it.
- A locked commit that is not 40 or 64 hex never reaches git. The entry is resolved again instead.
- Every git process ends with a kill of its whole group. If the leader exits on its own (for example by
  `RLIMIT_FSIZE`), it is waited for with `WNOWAIT`, so it is not reaped and its group id cannot be reused. Then the
  group is killed and the leader reaped, so any child it left dies too. The test waits up to 10 s for an init-reaped
  zombie to leave the group. That is a wait for a condition, not a fixed sleep.
- Outside the Files list, each small: `check` prints `use NAME: template T from library L (PATH)`
  (`cli/spec_cmds.py`, 3 lines). The authoring tools' `library` lists fetched templates (`library/author.py`, 1 line).
  `schema/ergostat.schema.json` gains `libraries` (the schema forbids unknown top-level keys). The agent guide says
  never to add `trust: owner` to a fetched library or edit the lock to make one load.

Overrun reason: 719 net lines against 560. The plan review added work the budget did not include: the swap rollback, the `git archive` timer and group kill, killing each group without reaping its leader (a group left alive was a real flake while building), the locked-commit check, the `files.tree` replay table with its noting, and the schema entry (19 lines). `fetch.py` is 266 lines against 170; everything else is close to its share.

### Round 2: the review's two findings

1. **A link through another link (blocking).** `tree.extract` no longer reads only a target's text. After every
   member is listed, each link's target is walked one step at a time from the link's folder. It is refused if a step
   goes above the copy's top, or if any step before the last lands on another link member, because that link's own
   target would move the walk. So `x/s -> ..` plus `x/y -> s/../..` is refused, in either archive order. A link
   that ends on another link is kept (`x/y -> s`), since that link is checked the same way. The new cases are in
   `test_symlink_hashed_not_followed`, along with a kept case whose real path is the copy's top. SPEC §2a and
   SECURITY.md now describe this rule instead of "links that stay inside". Mutant: with the through-link check
   removed, the test fails (`DID NOT RAISE Refused`).
2. **`os.waitid` on macOS.** This session runs on Linux, so I could not run `python -c 'import os; os.waitid'` on the
   Mac. I took the finding as true, because CPython 3.12 (the floor in `pyproject.toml`) leaves `os.waitid` out on
   Apple platforms. Where `os.waitid` is missing, `fetch._exited` now reaps the leader with `poll`/`wait` and kills
   its group right away. While any child is left in the group, POSIX does not give that id to a new process. The
   one gap: if the group is already empty, another process could take that id as a new group in the few
   microseconds before the kill. Where `waitid` exists, nothing changed. New test `test_fetch_without_waitid` removes
   `os.waitid` and checks two things: a stalled git's group is killed with no `.tmp-` folder left, and a real fetch
   locks with every group gone. Mutant: with the `hasattr` guard removed, it fails with `AttributeError`. Not run:
   `test_library_fetch.py` on macOS itself.

All 19 tests in `tests/test_library_fetch.py` pass. `tests/test_cli_fallback.py`, `tests/test_templates.py` and
`tests/test_modelling_template.py` pass unchanged (59). Ruff is clean. `git merge main`: already up to date.

Overrun reason: about 743 net lines against 560. Round 1's reasons stand. Round 2 adds about 24 lines: the stepwise
link walk (13) and the fallback for platforms without `os.waitid` (9).

### Round 3: the review's finding

1. **A link through another link on a case-insensitive disk (blocking).** On APFS, `x/S -> ..` plus `x/y -> s/../..`
   passed: the step `x/s` was compared as text against `{x/S, x/y}`, yet on disk `x/s` opens `x/S`. There are two
   fixes, both in `tree.extract`:
   - Names are compared through `tree._key` (NFC, then `casefold`) in the walk that refuses a link through another
     link, and in the "members under a link" check. So `x/s` is `x/S`, and an NFC `é` is the NFD `é`. APFS ignores
     both differences.
   - Once the links are made, each link's `os.path.realpath` must stay under the copy's own `realpath`. A link that
     does not is refused as `a link out of the copy on disk`, and `TMP` is removed as on any refusal. This check does
     not depend on how a file system folds names: it asks the disk where the link leads.

   New cases in `test_symlink_hashed_not_followed`: `x/S -> ..` with `x/y -> s/../..`; an NFD `x/é -> ..` with an NFC
   `x/y -> é/../..`; and `L -> sub` with `l/x.yaml`. Each fails without the fix even on this case-sensitive Linux disk,
   because the text check is what refuses them. One more case patches `_inside` to do nothing and shows that the
   `realpath` check alone refuses round 2's `x/s -> ..` with `x/y -> s/../..`. SPEC §2a and SECURITY.md state both
   rules.

   Mutants, each applied, run and reverted: `_key` returning the name unchanged fails the test (`DID NOT RAISE
   Refused`), and so does `_key` without NFC (`casefold` only). With the `realpath` check removed, the test also fails.

   Not run: the test on macOS itself (this session runs on Linux).

All 19 tests in `tests/test_library_fetch.py` pass. `tests/test_cli_fallback.py`, `tests/test_templates.py` and
`tests/test_modelling_template.py` pass unchanged (59). Ruff is clean. `git merge main`: already up to date.

Overrun reason: about 754 net lines against 560. The reasons from rounds 1 and 2 stand. Round 3 adds about 11 lines in `tree.py`: the case-insensitive name key, and the realpath check after the links are made.

### Round 4: the merge of main

The factory's merge of main (b71c54f8) conflicted in `ergostat/cli/__init__.py`, and only in the help text: main
added a `worker` line in the same place where this branch added `library`. Both lines are kept, and both topics are
still registered. No other code changed in this round. After the merge, these pass: `tests/test_library_fetch.py`
(19); `tests/test_cli_fallback.py`, `tests/test_templates.py` and `tests/test_modelling_template.py`, unchanged (59);
`tests/test_spec_schema.py` and `tests/test_spec_structure.py` (42); the other four `tests/test_library_*.py` files
plus main's new `tests/test_compute_worker_protocol.py` (141). Ruff is clean. Not run here: the whole unit suite, the
four browser files (no page changed) and `demo_check` (no example touched).

Overrun reason: about 754 net lines against 560, as in round 3 (737 under `ergostat/` and 19 in the schema). Round 4 adds none, and the reasons from rounds 1 to 3 stand.

## Where it stopped

Parked by the factory (reviewer, 2026-11-22 14:18).

Stopped on its last attempt by RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```
Traceback (most recent call last):
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 143, in main
    return judge(cfg, given["item"], began)
  File "/Users/user/ergostat-live/instance/dev/bin/review.py", line 195, in judge
    got = fac.session(cfg, "reviewer", text, wt)
  File "/Users/user/ergostat-live/instance/dev/bin/fac.py", line 669, in session
    raise RuntimeError(f"claude: {out.get('subtype')}: {str(out.get('result'))[:300]}")
RuntimeError: claude: success: You've hit your weekly limit · resets Nov 24, 3am (UTC)

```

### Round 5: continued after the reviewer's usage limit

The last park was not a review finding. The reviewer's session hit a usage limit and stopped before it judged the
branch, so there was nothing to answer and no code changed in this round. `git merge main`: already up to date
(main is at bf6dbebf, merged in 32dcb5af). After that, these pass: `tests/test_library_fetch.py` (19);
`tests/test_cli_fallback.py`, `tests/test_templates.py` and `tests/test_modelling_template.py`, unchanged (60);
`tests/test_spec_schema.py`, `tests/test_spec_structure.py` and `tests/test_compute_worker_protocol.py` (50). Ruff is
clean. Not run here: the whole unit suite, the four browser files (no page changed), `demo_check` (no example
touched), and anything on macOS (this session runs on Linux).

Overrun reason: 754 net lines against 560 (`git diff main --shortstat -- ergostat schema`: 778 added, 24 removed). Round 5 adds none, and the reasons from rounds 1 to 3 stand.

### Round 6: the merge of main, and the review's two findings

**The merge (6d2c7c1d).** Main (a08e4b3e) had landed `library-fetch-tree`, a cut-down rewrite of this branch's
`sources.py`, `tree.py` and `files.tree` with its own API and its own tests (`tests/test_library_tree.py`). It
conflicted in `sources.py`, `tree.py`, `uses.py`, `load.py` and SPEC, and `files.py` merged with two `tree` functions.
I resolved it onto main's modules and API, and adapted this branch's `fetch.py`, `fetched.py`, `cli/library.py` and
tests to them, so one walker, one hash and one extractor remain:
- `sources.py` is main's `check`/`SourceError(code, field)`, plus `trust:` (only `owner`) and `SHA`. NAME is narrowed
  to this definition's `[a-z][a-z0-9-]{0,63}` (main allowed `_`), and `+` is dropped from the URL and version
  allowlists (the definition's character sets have none). Main's version cap of 128 is kept (it is within "at most
  200"). The `git:` check stays main's single anchored regex, not `urlsplit`. It refuses everything the definition
  lists, and `test_bad_name_and_scheme_refused` and `test_sources_are_whole_matches` still pass.
- `files.tree` is main's walker (folder handles opened `O_NOFOLLOW`, `TreeError`, a `DEPTH` of 64), wrapped in this
  branch's noting. The walker records the listing in `Reads.trees` and the bytes in `Reads.files`, and replay answers
  from the snapshot. Main's version raised `NotKept` on every replay. That contradicts this definition's
  `test_fallback_reads_library_from_snapshot`, so the definition wins. Main's `test_not_read_while_replaying` still
  passes, because an empty snapshot has no such tree.
- `tree.py` is main's extractor, plus a `strip` for `path:`. Folders at or above the path are skipped, and a member
  outside it is refused. I also added `hashed(listing)`, the one hash. `digest(root)` and `read(root)` both use it, so
  load still hashes the bytes it parses. Two of main's rules are stricter than this branch was. A link that lands on any
  link is refused, even as its last step (this branch kept `x/y -> s`; the test's kept case is now `x/s -> ..`). Links
  are made as they arrive, not last. Nothing can be written through one, because folders are entered by `O_NOFOLLOW`
  handles and a member under a link is refused.
- One line of main's `tests/test_library_tree.py` changed: the refused-key message now reads "git, version, path and
  trust only". Two asserts are added there for `trust:`. In `tests/test_library_fetch.py`, only the expected messages
  and names changed (`tree.Refused` is now `files.TreeError`, `MAX_BYTES` is now `BYTES`, and so on).
  `test_sources_are_whole_matches` now goes through `sources.check`.

**Finding 1, `_git` without a kill on interrupt (blocking).** The poll loop is now in `try/except BaseException`, which
kills the group and re-raises. New test `test_interrupted_git_is_killed`: the fetch git stalls
(`sh -c 'sleep 60 & sleep 60'`), and a `KeyboardInterrupt` is raised from inside the poll. The test asserts the group
is gone and no `.tmp-` folder, copy or lock is left. With the fix removed, it fails: `DID NOT RAISE ProcessLookupError`.

**Finding 2, a `path:` not in the commit (blocking).** After the merge, main's `tree.extract` turns a `tarfile` error
into `TreeError`, and `run()` now catches `TreeError` and `tarfile.TarError`, so a refusal no longer crashes the
fetch. Also, `_archive` first `peek`s the pipe. If git wrote nothing, nothing is extracted, git is waited for, and its
non-zero exit becomes `git archive failed: <git's own message>`. New test
`test_path_fetches_its_folder_and_a_missing_one_is_reported` uses three libraries: `path: nope` (not fetched, said as
git's failure, no traceback); then `lib/sub` and `lib` (both fetched and locked, so the run goes on past the failure).
`lib/sub` holds only that folder's contents, and its template loads. With the `peek` removed, it fails (`bad-library-tree: '': empty file`).

Tests run after the merge, each file through `scripts/named_tests.py`: `tests/test_library_fetch.py` (21),
`tests/test_library_tree.py` (6), and `tests/test_cli_fallback.py`, `tests/test_templates.py` and
`tests/test_modelling_template.py`, all passing and unchanged. The other five `tests/test_library_*.py` files pass
(4 skipped: bwrap cannot make namespaces in this container). `tests/test_spec_schema.py`, `tests/test_spec_structure.py`
and `tests/test_compute_worker_protocol.py` pass. Ruff is clean. Not run here: the whole unit suite, the four
browser files (no page changed), `demo_check` (no example touched), and anything on macOS.

Size: `git diff main --shortstat -- ergostat schema` gives 556 added and 48 removed, so 508 net against main, within
560. That is only because about 257 lines of this gap (`sources.py`, `tree.py` and `files.tree`) are now on main
through `library-fetch-tree`. Counted whole, the gap is about 765 lines, and the reasons from rounds 1 to 3 stand for
that.

### Round 7: the merge of main (dc8ad98d)

Main had landed `library-fetch-git`, which says it "takes over `factory/library-fetch`'s `fetch.py`, trimmed to fit":
its own `fetch.py`, with its own API and its own tests (`tests/test_library_fetch_git.py`). The merge conflicted in
`fetch.py`, and in `spec/load.py` (main added `operating`, this branch `libraries`, to the same `TOP` line; both are
kept). As in round 6, I resolved it onto main's module and adapted this branch's CLI, loader and tests to it, so one
fetch remains:
- `fetch.py` is main's: `fetch(root, libraries, update, say)`, `FetchError(code, name, why)`, `read_lock` and
  `write_lock`, a whole bare `clone`, `rev-parse --verify VERSION^{commit}`, and `git archive COMMIT[:PATH]` written to a
  file in the temporary folder. So the folder poll and `RLIMIT_FSIZE` cover the archive too, and the archive timer,
  the `peek` and `tree.extract`'s `strip` are gone. The 120 s limit, the group kill (an interrupt included), the
  `waitid` fallback, the flock, the rollback and the link checks are main's. Three changes to it, each small:
  1. The lock entry and the "same entry" test use `git`, `version` and `path` only. Main used `sources.KEYS`, which
     now has `trust`, so `trust: owner` would have gone into the lock.
  2. An unchanged entry is kept only when the copy's tree hash is still the lock's (this definition's step 2). Main
     kept any copy that was there. With the hash check removed, the new assert in `test_altered_copy_refused` fails:
     the altered copy says "up to date".
  3. `argv()` and `_start()` are split out of `_run`, so the tests can record and stall git calls.
- `tree.digest` and `tree.hashed` now return `sha256:…`, the definition's lock form. Main's tests compare digests
  only with each other, so they pass unchanged. The caps are read when the function is called, not bound when it is
  defined, so a test that patches `tree.BYTES` reaches fetch.
- `libraries.lock` is main's flat `{NAME: {git, version, path?, commit, tree}}`, with `path` left out when there is
  none. `fetched.py` reads that shape, and it compares `path` as given. SPEC §2a says so.
- `cli/library.py` calls `fetch.fetch` for one library at a time. A refused library is said
  (`library NAME: not fetched: CODE: …`) and the next one is still fetched (rc 1). A `bad-lock` or
  `linked-library-folder` stops the command with rc 2. "waiting for the libraries lock" goes to stderr. Each
  library's read, decide and write is under the flock, and the lock is read again inside it, as main does.
- Where main differs from this definition, main's behaviour is kept, because main's merged tests pin it. This is
  reversible:
  - A same entry whose copy is missing resolves `version` again rather than fetching the locked sha, and is refused
    (`lock-mismatch`) when that is not the lock's commit and tree.
  - The clone is whole, not `--depth 1`.
  - The poll runs every 0.05 s, not every 0.25 s (stricter). SPEC and SECURITY now say 0.05 s, and they describe
    the archive as a file.
- `tests/test_library_fetch.py` changes only hooks, messages and the lock's shape: `_start`'s arguments,
  `write_lock` for `_swap` and `_write_lock`, `SIZE` for `CEILING`, `clone` for `fetch`, "still running after" and
  "bad-lock", and `git-failed: archive`. The `--end-of-options` check now looks at `clone` (URL after it) and
  `rev-parse` (REF after it). Two asserts are added: the lock entry holds no `trust`, and an altered copy is
  fetched again. I saw each one fail with its guard removed.

Tests run after the merge, each through `scripts/named_tests.py`:
- `tests/test_library_fetch.py`, `tests/test_library_fetch_git.py` and `tests/test_library_tree.py`: 40 pass. Main's
  two files are unchanged.
- `tests/test_cli_fallback.py`, `tests/test_templates.py` and `tests/test_modelling_template.py`: 61 pass, unchanged.
- `tests/test_spec_schema.py`, `tests/test_spec_structure.py` and `tests/test_compute_worker_protocol.py`: 58 pass.
- The other five `tests/test_library_*.py` files and `tests/test_todo_template.py`: pass, with 4 skipped because
  bwrap cannot make namespaces here.

Ruff is clean. Not run here: the whole unit suite, the four browser files (no page changed), `demo_check` (no example
touched), and anything on macOS.

Size: `git diff main --shortstat -- ergostat schema` gives 304 added and 53 removed, so 251 net against main, within
560. Counted whole, with what main now holds of it, the reasons from rounds 1 to 3 stand.

### Round 8: the review's two findings

1. **A re-fetch resolved `version` again instead of the locked commit (blocking).** When the entry is unchanged and
   `--update` is not given, but the copy is missing or altered, `fetch._one` now passes the locked commit to `_get`.
   `_get` resolves it with `rev-parse --verify --end-of-options COMMIT^{commit}` in the full clone and archives it.
   The commit has already passed the hex check, so it never reaches git as an option. If that commit's tree is not
   the lock's, the fetch is still refused (`lock-mismatch`), and the copy and lock are left as they were. If the
   locked commit is gone upstream, git's own failure is reported (`git-failed: rev-parse`).
   - New test `test_refetch_restores_the_locked_commit_after_the_branch_moved`: `version: main` is fetched, main
     moves upstream, and the copy is deleted. `fetch` without `--update` brings the copy back at the locked commit and
     tree, the lock is byte for byte unchanged, `rev-parse` was given the locked commit, and load succeeds. Then
     `--update` moves the pin.
   - Main's `tests/test_library_fetch_git.py::test_fetch_writes_lock` pinned the old behaviour (a moved tag gave
     `lock-mismatch`). It contradicts this definition, so the definition wins, as in round 6. That case now asserts
     that the copy comes back at the locked commit with the lock unchanged. Its `lock-mismatch` case is kept: a lock
     entry whose tree is not the locked commit's is refused, with no copy made and the lock untouched. The rest of
     that test is unchanged.
   - Mutant: with `_get` given `version` again, both tests fail (`lock-mismatch` on the moved branch).
   - SPEC §2a now says the locked commit is fetched again, even if `version` has moved since.
2. **The GAPS.md splice (lesson 7).** The `library-fetch` clause had been put inside main's text, between
   "**Built**" and `(library-sandbox-sensors-proven)`. Main's text is now restored as it was, and the `library-fetch`
   *Built* clause follows its *Left* line. There is one *Still needed* clause. It no longer lists fetch by git URL, a
   lock entry without a tree, or hashed symlinks, and it keeps fetch by package, the provenance gate and the sandbox
   for libraries without `trust: owner`.

Tests run, each through `scripts/named_tests.py`:
- `tests/test_library_fetch.py`, `tests/test_library_fetch_git.py` and `tests/test_library_tree.py`: 41 pass.
- `tests/test_cli_fallback.py`, `tests/test_templates.py` and `tests/test_modelling_template.py`: 61 pass, unchanged.
- `tests/test_spec_schema.py`, `tests/test_spec_structure.py` and `tests/test_compute_worker_protocol.py`: 58 pass.

Ruff is clean. `git merge main`: already up to date. Not run here: the whole unit suite, the four browser files (no
page changed), `demo_check` (no example touched), and anything on macOS. One command was refused in this session: a
`python3 - <<'EOF'` heredoc that edited `fetch.py`. I made the same edits with the editor instead.

Size: `git diff main --shortstat -- ergostat schema` gives 315 added and 61 removed, so 254 net against main, within
560.
