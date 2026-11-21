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

### Round 3, third try
Bash was refused from the first command of this session, so `git rm .gitattributes` could not run, and neither
could `git commit`; this paragraph is therefore uncommitted in the worktree. Nothing else changed. What is left is
still the one command: `git rm .gitattributes && git commit`. The implementor needs Bash (at least `git rm` and
`git commit`) to do it; this is a tool permission, not a design question.

### Round 3, fourth try
Same as the third: the first Bash command (`git rm .gitattributes`) was refused, so nothing could be removed or
committed, and this paragraph is uncommitted too. Sending the gap back to the implementor again will give the same
result until the session can run `git rm` and `git commit`; the coordinator can instead run
`git rm .gitattributes && git commit` on the branch itself. Nothing else is left.

### Round 3, fifth try
The same again: Bash was refused on the first command (`git rm .gitattributes`), so the file is still there and this
paragraph is uncommitted. `docs/.gitattributes` and `dev/knowledge/.gitattributes` are still in place. A sixth try
will get the same result. The fix is for the coordinator to run `git rm .gitattributes && git commit` on
`factory/gaps-md-no-collisions`, or to give this session Bash.

### Round 4
This time read-only Bash worked (`git status`, `git log`, `cat`): the tree was clean, and the root `.gitattributes`
still holds the same two rules as `docs/.gitattributes` and `dev/knowledge/.gitattributes`. `git rm .gitattributes`
was refused again, so the file is still committed (`git commit` did work, so this paragraph and the three
before it are now committed). What is left is still one
command, for whoever is allowed `git rm`: `git rm .gitattributes && git commit`.

### Round 4, second try
Bash was refused on the first command (`git status --short && git rm .gitattributes`), so the root
`.gitattributes` is still committed and this paragraph is uncommitted. Nothing else changed. I did not delete it
with the file tools instead, because that is the same removal the refusal blocked, done another way. Another
retry will end the same way. The coordinator can run `git rm .gitattributes && git commit` on this branch, or give
the implementor Bash with `git rm` and `git commit`.
