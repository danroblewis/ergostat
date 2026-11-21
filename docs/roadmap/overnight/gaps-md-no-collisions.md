# gaps-md-no-collisions: finishing a gap no longer collides on docs/GAPS.md or breaks a test

depends-on: []

Measured 2026-11-21: `docs/GAPS.md` changed in 13 of the last day's merges and caused queue conflicts, each sending a reviewed gap back. `tests/test_backlog.py::test_intake_done_rule_on_the_real_gaps_md` pins the live status of real entries, so any gap that correctly marks one of them done fails the merge queue (it just cost a batch of three a bisection, about 25 extra minutes).

## Definition of done
- `tests/test_backlog.py` tests the done rule on a fixture `GAPS.md`, covering each shape the pinned entries covered (a parenthetical across lines, superseded, parked, open). No test depends on the current status of a real entry.
- Two gaps that each edit different entries of `docs/GAPS.md` merge without a conflict (`.gitattributes`: `docs/GAPS.md merge=union`). The same for `dev/knowledge/review-lessons.md`, where 4 of the 5 conflicting pairs among approved gaps are.
- A union merge cannot silently leave an entry twice or in two sections: `ergostat`'s intake says so as a dependency-style problem, and a test shows it.

## Files to touch
`.gitattributes` (new), `tests/test_backlog.py`, `dev/bin/intake.py`.

## Risks
- lesson-3: a duplicated entry must be reported, never resolved by picking one.

## Acceptance tests
- `tests/test_backlog.py::test_the_done_rule_on_a_fixture`
- `tests/test_factory.py::test_two_gaps_editing_gaps_md_merge_cleanly`
- `tests/test_backlog.py::test_a_duplicated_gaps_entry_is_reported`
- `tests/test_factory.py::test_two_lessons_editing_review_lessons_merge_cleanly`

## Size budget
30 net lines of code outside `tests/` and `docs/`.

## Where it stopped
Built in full; nothing is left. 24 net lines: 22 in `dev/bin/intake.py` and 2 in `.gitattributes`.

Choices made with nobody to ask (each the one easiest to undo):
- An entry listed more than once is neither found nor closed. If the intake has a gap for it, that gap gets a
  dependency problem naming every line and section. If not, it is said on stderr. Removing the extra copy by hand
  clears it on the next run. The intake never picks one copy (lesson-3).
- Duplicates are counted in every section, *Done recently* included, so an entry left both open and done is caught.
- `tests/test_backlog.py::test_intake_done_rule_on_the_real_gaps_md` is removed. Each shape it pinned is now an entry
  in the fixture of `test_the_done_rule_on_a_fixture`, which replaces `test_intake_done_rule_on_a_gaps_fixture`.
- Each merge test also runs the same merge without `.gitattributes` and asserts that it conflicts. The GAPS test also
  shows that edits to entries side by side merge but leave both entries twice, which `twice()` reports.
- origin/main was not merged in: this clone has no origin ref, and local `main` is not ahead of the branch.

### After the scratch-files gate (same round)
The gate refused the new top-level `.gitattributes`, though Files to touch names it. Git reads a `.gitattributes`
in any folder, so each rule now sits beside the file it merges, in a folder main already has:
`docs/.gitattributes` (`GAPS.md merge=union`) and `dev/knowledge/.gitattributes` (`review-lessons.md merge=union`).
`merge_two` in `tests/test_factory.py` copies the folder's file, not the root one, so the two merge tests show that
the folder files work on their own (both pass; each still conflicts without them).

**Left:** the top-level `.gitattributes` is still committed. Removing it needs `git rm .gitattributes`, and this
session's tools refuse `git rm` (it is not among the implementor's allowed commands here). Its two rules duplicate
the folder files, so removing it changes no behaviour. Whoever has `git rm` should run it and commit.

### After the scratch-files gate again (same round)
The gate refused the root `.gitattributes` a second time. `git rm .gitattributes` was refused again in this
session, and so was every later Bash command (even `git check-attr`). I did not get around the refusal with a plain
`rm` and `git add`, since that does the same removal by another route. What is left is the same one command:
`git rm .gitattributes && git commit`. The rules in the two folders are unchanged.
