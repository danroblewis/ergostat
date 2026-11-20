# continue-branch: a gap can continue an existing branch, with main merged in by the factory

depends-on: []

Branch `continue-branch`, from main. Asked by the coordinator: gap/warm2 and gap/warm3 were parked by the kill rule
because a continued branch (seeded by hand into the drop as factory/<name>) never got origin/main merged in: the
implementor's session was refused `git merge` three times, and the reviewer (rightly, lesson-7) would not pass a branch
63 commits behind main whose daemon code had conflicted with main before. Gate 1 also failed: a continued gap's
definition file is not its branch's first commit. Today continuing a parked branch is a manual intervention
(seeding drop.git), twice tonight.

## Definition of done

A gap request may name `continues: <branch>` (an existing branch in the checkout, e.g. a parked one). The intake
fetches it into the drop as the gap's factory/<branch> (refusing names that fail the branch rule). Before every
implementor session on a branch that is behind main, implement.py (the program, not the AI) merges origin/main into the
work clone: a clean merge is committed as the factory; a conflicted one is handed to the session with the conflict list
in its brief, and the session may run `git merge`, `git add`, `git commit` and `git status` to finish it (and nothing
that reaches a remote). The fast suites run after the merge. The reviewer's gate 1 accepts, for a continued gap, the
original branch's definition file as the definition (its first commit on that branch), and checks the merge base is
current main. The README says how to continue a parked branch.

## Acceptance tests

- `tests/test_factory.py::test_a_gap_continues_a_named_branch`: the branch fetched into the drop; the implementor starts on it.
- `tests/test_factory.py::test_a_branch_behind_main_has_main_merged_before_the_session`: a clean merge committed by the program.
- `tests/test_factory.py::test_a_conflicted_merge_is_handed_to_the_session_with_its_conflicts`: the brief lists them; the allowed git commands include merge/add/commit.
- `tests/test_factory.py::test_gate_one_accepts_a_continued_branch_definition`.

## Size budget

250 net lines of code outside `tests/` and `docs/`.
