# code-reduction-map: a reviewed map of what ergostat's code can lose, each item with its evidence

depends-on: []

The owner, 2026-11-21: before ergostat is given to people, review and reduce the amount of code. This gap makes the map; later gaps do the cuts.

## Definition of done
1. `docs/proposals/code-reduction.md`: for `ergostat/` and `dev/bin/`, the candidates to delete, merge or simplify, each with: the files and lines, the evidence (no caller on main, a duplicate of named code, a superseded path named in SPEC or GAPS, a feature flag never set), the net lines it would remove, the risk, and the tests that cover it.
2. Ranked by lines removed per unit of risk. The total is stated, and so is what was looked at and not found removable.
3. The first ten items written as gap definitions in the house shape (definition of done, files, risks, acceptance tests, size budget).
4. No code changes. Every claim cites file:line on main.

## Files to touch
`docs/proposals/code-reduction.md` only.

## Risks
- lesson-8: "no caller" is checked with grep over the whole repository, tests and docs included, and says what was searched.

## Size budget
0 lines of code; the map under 700 lines.

## Where it stopped

Built: `docs/proposals/code-reduction.md` (478 lines). It has eleven ranked items, about 1,160 net lines in all, what
was looked at and not found removable, and the first ten written as gap definitions. No code was changed.

Choices taken without asking, the more reversible each time:
- `scripts/code_evidence.py` was not run, because this session's shell refused `python3`/`uv run python` (and `awk`,
  redirection, and `git grep -f`). Its "dead" rule was applied instead with `git grep -o -w … | sort | uniq -c` over
  every tracked file, docs included. The map says so (§1), and the dead-names gap's acceptance test runs
  `code_evidence.py` to confirm.
- For `ergostat chat`, the map proposes a new brief from the agent guide, not deleting the command (the Supervisor is a
  NOTES.md term). Deleting it is left to the owner.
- Item 11 (the Node/Java/Go re-signing migration) is not written as a gap. It is worth about 7 lines, and it needs the
  owner's word on old records.

## Where it stopped

Parked by the factory (review/code-reduction-map-2, 2026-11-22 03:19).

Done: docs/proposals/code-reduction.md, with 11 ranked items (≈1,157 net lines), the search method, what was looked at and not found removable, and 10 gap definitions. No code was changed. Left: item 2 and code-cut-toml-format must list all ~20 sites that only matter for a TOML model (or say which stay and why), handle the second mdl.parse caller at cli/spec_cmds.py:149, recount item 2's lines and score, and make the gap's Files list agree with its grep check. Parked because the review-1 finding was not answered and this is the second failed review.

## Where it stopped

Continued (gap/code-reduction-map-continued, round 1). The map is now 555 lines. No code was changed.

Each finding of review/code-reduction-map-1 and -2, and what was done about it:
- Item 2 was missing the ~20 TOML-only sites. Item 2 now has two tables that cover all 26 files `git grep -n
  "ergostat.toml" -- ergostat` matches on 277a9c6c. "Removed" lists 11 sites, ≈482 net lines. "Stays, and why" covers
  `find` and the fast path (kept, so that a TOML folder is refused rather than read as "no model"; lesson-3), the
  sites items 3 and 6 remove, and the 21 `spec is None` guards. Those guards are left for the old-model migration,
  because they are 21 of 111 such reads in 50 files. The survey found three things the first draft missed:
  `spec/convert.py` has two other importers (`blockdiagram.py:1494`, `spec/discover.py:96`), so it can't be deleted
  whole; `model.check`'s body after `:610-613` is TOML-only (92 net); and `cli/running.py:133-136` starts the old
  runner only for TOML.
- The second `mdl.parse` caller, `cli/spec_cmds.py:149`: `cmd_convert` (`:142-168`) is now in the Removed table and
  in the gap.
- Recount and score: item 2 went from ≈330 / 110 to ≈482 / 161. It is still ranked second. The total went from
  ≈1,157 to ≈1,309.
- The gap's Files list vs. its grep check: code-cut-toml-format's DoD 5 names the exact 20 files the grep must list
  after the cut, and a new acceptance test compares them. Its Files list is exactly the files of DoD 1, 2, 4 and 6,
  and none of DoD 5's list is edited.
- Review-1, non-blocking: Python was not run. It still wasn't: `uv run python -c "print(1)"` and `uv run python
  scripts/code_evidence.py --help` were refused again, and so were a shell `for` loop over `git grep` and a
  `git diff … | grep | sed | sort -u | tr` pipeline. §1 says so, and says that names added to main after 1336e50e were
  not put through the dead-name pass. The "every other variable read is set or documented" claim was narrowed to what
  was done: a reading of 34 names, not a trace of each one.
- Every line reference was moved to main at 277a9c6c, since main changed 67 files after the first draft's base. The
  §1 last paragraph lists what was re-read. The 11 dead names were searched again: still dead.

Choice taken without asking, the more reversible one: the 21 guards and `runner.Runner` are listed but not given to
the TOML cut. They are left for a surveyed old-model migration, and they are not counted in the total.
