# remote-and-libraries-library-update-check: An update to a library is reviewed before it is taken: what the new version breaks and changes

depends-on: [library-fetch]

Problem: docs/proposals/external-systems.md (Deployment): 'Updating a pinned version is a reviewable change: ergostat check against the new version lists what broke, which numbers you depend on moved'. library-fetch's `fetch --update` resolves and swaps in the new commit at once; the first sign of trouble is a broken model after the swap. Nobody, agent or owner, can see an update's effect before taking it, and nothing says a newer version exists.
Change: a dry run that fetches the candidate into fetch's temporary folder (same allowlists, caps, timeouts and flock), never swaps it or writes the lock, compiles the model twice in memory (the locked copy and the candidate) and reports the difference.
Definition of done:
1. `ergostat library fetch NAME --update --dry-run` and an MCP tool `library_update` (name, optional version) do the same: resolve the entry's version (or the one given, checked by library-fetch's ref allowlist), fetch into a mkdtemp folder under .libraries, and remove it afterwards whatever happens; .libraries/NAME and libraries.lock are unchanged (asserted by hash in the test).
2. The report: commit from -> to, and the tags pointing at commits newer than the pinned one when the remote lists them (one `git ls-remote --tags` under library-fetch's git environment, refused schemes and refs as fetch refuses them); templates added and removed; per use of the library: parameters added, removed, newly required, defaults changed, exports removed (when template-exports has landed, else omitted); parts the instance makes added and removed by full name; parameter values that moved (name, from, to); errors and findings the candidate model has that the current one does not (a broken reference first).
3. Exit 0 when the candidate compiles with no new error, 1 otherwise; the MCP answer says the same as `ok`.
4. Nothing of the candidate reaches the running model, the good-model snapshot or the record.
5. SPEC §2a, AGENT-GUIDE ('before taking an update, run library_update and show the owner what breaks'), GAPS.
Files: ergostat/library/compare.py (new: the two compiles and the diff), ergostat/library/fetch.py (fetch into a folder without swapping), ergostat/cli/library.py, ergostat/mcp.py, docs/SPEC.md, docs/AGENT-GUIDE.md, docs/GAPS.md, tests/test_library_update.py (new; file:// repositories built in tmp_path).
Acceptance tests: test_dry_run_changes_nothing (copy and lock hashes equal before and after; no .tmp- folder left); test_report_lists_removed_param_and_part (upstream removes a parameter and a stock the owner references: both listed, the broken reference first, exit 1); test_report_lists_moved_value; test_report_names_newer_tags; test_bad_version_refused_without_git; test_mcp_library_update_matches_cli.
Size budget: 260 net lines.

Area: remote-and-libraries. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.

## Where it stopped

Built, round 1: every definition-of-done item is in the code, with its acceptance test. 260 net lines outside tests,
docs and dev (the budget).

- Item 1: `fetch.candidate(root, name, src)` holds the libraries flock for the whole review (the fetch, both compiles
  and the diff, so no fetch can swap the copy between them: lesson 1), fetches with fetch's own `_get` (same git
  environment, caps, time limit) into a `mkdtemp` `.tmp-` folder, and removes it in `finally`. The flock code of
  `fetch` moved into `fetch.held`, shared by both. A version given to `library_update` passes `sources.check` before
  any git process (test_bad_version_refused_without_git: `calls == []`). test_dry_run_changes_nothing hashes every
  file under the project (the copy and the lock among them) before and after;
  test_dry_run_removes_its_folder_when_it_fails covers a failing compile.
- Item 2: `library/compare.py`. Tags: one `git ls-remote --tags --end-of-options URL` under `_run`, names kept only
  when they match the `version:` allowlist, then `rev-parse --verify` of the pinned commit and
  `rev-list --ancestry-path ^PINNED SHA...` in the clone. When that cannot be told (a git failure or limit, the pinned
  commit gone upstream, more than 1,000 tags) `tags` is null with `tags_why`, never an empty list
  (test_tags_that_cannot_be_told_are_unknown_never_none). template-exports has landed, so exports removed are given.
- Item 3: rc 0/1 from `ok`; test_mcp_library_update_matches_cli checks the command's lines are `compare.lines` of
  the MCP answer.
- Item 4: the candidate is compiled with `fetched.OVER` (a context variable) standing in for NAME's copy and lock
  entry, never a file; `compare` opens no Project, so nothing is recorded, and `goodmodel.keep` is not called.
  `files._NOW` is set to None during both compiles so a surrounding snapshot recorder notes nothing; no test opens
  such a recorder around it.
- Item 5: SPEC §2a (*Before an update*), AGENT-GUIDE (*Templates from a folder the owner did not write*). GAPS: the
  entry is below, as the house rules say (a branch editing docs/GAPS.md is refused).
- Choices made alone (each the most reversible, a line or two):
  - `ergostat/library/fetched.py` changed although not in the Files list: the context variable is the smallest way to
    compile the candidate without writing the lock or the copy.
  - The command takes no version (the definition gives one to the MCP tool only); `--dry-run` needs `--update` and
    exactly one NAME, else rc 2. A fetch failure is rc 1, an unreadable lock or linked folder rc 2, as fetch.
  - "Parameter values that moved": the use's parameter values as expanded, and the model `parameters:` the use makes
    (`parameter.INSTANCE-NAME`, their `value`). A number a template writes straight into a part's field is not
    compared (said in SPEC).
  - A problem is new when no current problem has its level, code, `about` and message (the temporary folder's path
    in a message read as `.libraries/NAME`). Errors first; among them `unknown-ref` and `bad-ref` first.
  - For a library without `trust: owner`, defaults and values are marked as the library's text and problems as
    `check` marks them (test_untrusted_librarys_values_are_marked); names are references, not marked.
- Tests shown to fail when the code they guard is broken: the broken-reference ordering removed
  (test_report_lists_removed_param_and_part fails); the tag filter made to keep every tag
  (test_report_names_newer_tags fails); the temporary folder left in place (four tests fail).
- Not run here: the whole unit suite and the four browser files (the factory and merge queue run them; no page is
  changed). Run: tests/test_library_update.py (9 passed), tests/test_library_fetch.py (22), test_spec_mcp_explain.py,
  test_gated_actions.py; ruff clean. Local main had nothing past this branch's base to merge.

Round 2, answering the one review finding (blocking; there were no others):

- 'Values moved' took the model parameters a use makes by the prefix `inst + "-"`, so `t` was given `t-x`'s, and a
  `once` template's unprefixed ones were never compared. Fixed by recording what the use made: the use record in
  `library/uses.py` now carries `parameters` (the names from the expansion's `parameters:` section, as it already
  records `parts`), and `compare` compares only the names that use made in both compiles. SPEC §2a *Before an update*
  says so instead of `parameter.INSTANCE-NAME`. New test test_moved_values_are_the_uses_own: uses `t` and `t-x` of
  one template and `h` of a `once` template, values moved in all three. With the old prefix rule it fails on both
  counts (`t` lists `parameter.t-x-rate`, `h` lists nothing); with the fix it passes.
- `library/uses.py` is outside the Files list: one key added to the record the use already writes, the smallest way
  to know what a use made (the finding's own fix).
- Run: tests/test_library_update.py (10 passed); test_library_fetch.py, test_templates.py, test_library_trust.py
  (109 passed); test_library_untrusted.py, test_library_fetch_load.py, test_library_sandbox_sensors.py (38 passed,
  4 skipped: bwrap cannot make its namespaces in this container, unrelated); ruff clean. Not run here: the whole unit
  suite and the four browser files (no page changed). Local main has nothing past this branch's base.
Overrun reason: 261 net lines against a budget of 260; the one line over is the round-2 fix recording which parameters each use made, which the review asked for.

Round 3, answering the one finding (blocking: a conflict with main in docs/AGENT-GUIDE.md; there were no others):

- Merged main (d0f95413). The conflict was two paragraphs added at one place: main's `LIB/TEMPLATE` naming of a
  fetched library's template, and this branch's *Before taking an update* paragraph. Both kept, as separate
  paragraphs. No code conflicted; main's qualified-use change to library/fetched.py, uses.py and mcp.py merged clean.
- The `## Entry` had no `section:` line, which dev/bin/gapsdoc.py refuses; it now says `section: Remote systems and
  libraries`, and its bullet begins with the gap's full title, which is how the factory finds an entry.
- Run after the merge: tests/test_library_update.py (10 passed); test_library_fetch.py, test_library_qualified.py,
  test_templates.py (73 passed); ruff clean. Not run here: the whole unit suite and the four browser files (no page
  changed).

## Entry

section: Remote systems and libraries

- **An update to a library is reviewed before it is taken: what the new version breaks and changes** (SPEC §2a, *Before an update*): `ergostat library fetch NAME
  --update --dry-run` and the MCP `library_update` (name, version) fetch the candidate into a temporary folder under
  the libraries flock, never swapping it in or writing the lock, compile the model on both in memory, and report the
  commits, newer tags, templates added and removed, per use the parameters, defaults, exports, parts and values that
  moved, and the new errors and findings (a broken reference first); exit 1 when it adds an error. *Left*: what the
  candidate does when run (only what it compiles to is compared).
