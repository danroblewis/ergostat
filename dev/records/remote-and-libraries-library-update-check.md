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
