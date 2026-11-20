# warm3: warm processes for blocks, the rounds after warm2

The continuation of the same gap (branch `warm3`, now `factory/warm3`). Its definition of done, acceptance tests and
size budget are those of [warm2.md](warm2.md); this file keeps only where each of warm3's rounds stopped. The rounds
after this file's own are recorded at the end of `warm2.md`.

## Where it stopped (warm3, round 1, 2026-11-20)

- **CPU after `done` (fixed):** SPEC §9.7 and `daemons/usage.py` now say what the code does. CPU used after `done`
  and before the next hand-over belongs to no run: it is the process's own, left over with its start-up. Only CPU
  used after the next hand-over's snapshot is that run's. The new test
  `test_cpu_used_after_done_and_before_the_next_hand_over_is_no_runs` has a program spend 0.6 s of its own CPU after
  each `done`, and asserts that neither run is charged it. With the hand-over snapshot left stale, it fails (0.6 s
  charged to the second run).
- **`--check-warm FILE` errors (fixed):** a FILE that is missing or unreadable, is not JSON, or is JSON but not an
  object, is now said on stderr with the file named, nothing run, rc 2. The test is
  `test_the_check_says_what_is_wrong_with_its_file`. Without the object check, it fails with a traceback.
- **rc overlap (warm2-2's non-blocking finding):** "nothing concluded" (not deterministic, or no strict `done`) is
  now rc 3, and rc 2 stays the CLI's usage error. SPEC §9.7 says so, and the two tests that asserted 2 assert 3. This
  is the more reversible choice: one number in `warmcheck.check`, documented.
- `tests/test_warm.py` (20) and `tests/test_daemons.py` pass. Ruff is clean. Size: about 15 more net lines of code.
- **Not done: merging `main`.** This session was again refused `git merge` (and `git merge-tree`, so I could not
  even preview conflicts). I did not work around that by hand. `main` is 56 commits ahead. The factory's merge, and
  the four suites run after it under the watchdog, remain before this branch is done. I did not run the four suites
  myself (the factory runs them).

## Where it stopped (warm3, round 2, 2026-11-20)

- **Blocking, still open: `main` is not merged in.** This session was refused `git merge` for the third time. I
  could not even run `git log` to list main's commits. Copying main's 56 commits in by hand would be a merge that git
  does not know about, and hard to undo, so I did not do it. The factory must merge `main` and then run the four
  suites under the watchdog. The likely conflicts are docs/SPEC.md, docs/GAPS.md, docs/AGENT-GUIDE.md,
  ergostat/spec/ir.py, ergostat/web/server.py, schema/ergostat.schema.json, and the daemon code.
- **Gate 1 ("the definition is not the branch's first commit"):** `warm3.md` is 7dda276. It is the first commit
  after warm2's own history, which this branch continues. Rewriting that history with a rebase is hard to undo and
  was not asked for, so I left it. The factory decides whether that is acceptable.
- **docs/GAPS.md (fixed):** the entry now names `warm3`, says it is not done, and says why.
- Run after this round: `tests/test_warm.py` 20 passed, `tests/test_daemons.py` 26 passed, ruff clean. No code
  changed this round.

## Where it stopped

Parked by the factory (review/warm3-2, 2026-11-20 06:34).

Failed its gates twice (the kill rule). Blocking findings:
- gate 1: docs/roadmap/overnight/warm3.md is not the branch's first commit
- docs/roadmap/overnight/warm3.md:160-163,167-172 (lesson-7): origin/main is still not merged in. The merge base is fdf83b9 and main is 63 commits ahead. The four suites have not been run after a merge. Merging main is the first thing this gap (warm3) names and a house-rule condition for done. Main has changed SPEC, GAPS, AGENT-GUIDE, spec/ir.py, web/server.py and the schema since the merge base, all of which this branch also edits, and the daemons/supervisor code this branch rewrites (proc.py, supervise.py, work.py) conflicted with main once before (61cd918). The implementer was refused `git merge` three times, so whoever has permission (the factory) must merge, resolve, and run the unit suite and the four browser files under suite_watch with rc 0 before this reaches the main people install.
