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
