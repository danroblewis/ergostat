# implementor-clone-has-no-remote: implementors and reviewers are told that the implementor's clone has no remote, so a true report is not failed as a false one

depends-on: []

`dev/bin/agents.py:305` (`publish`, called from `dev/bin/implement.py:203`) runs `git remote remove origin` in every implementor's clone before the session, by design. Reviewer clones keep the remote. `dev/prompts/implementor.md` does not say so, and `dev/prompts/reviewer.md:8` tells reviewers to compare with `origin/{base}`. So an implementor correctly reports that `origin/main` is an unknown revision, and a reviewer, looking in a different clone, fails it under lesson-8 as a false claim. Of 646 implementor transcripts, 107 hit this error. All 167 implementor clones on disk have no remote refs; all 169 reviewer clones have them. It ended `gap/run-budget-ledger` at the kill rule and left an item of `gap/queue-takes-all-ready` undone.

## Definition of done
1. `dev/prompts/implementor.md` says: the clone has no remote by design, `origin/*` does not exist there, local `main` is the base as of the clone, and other gaps' branches are absent. Neither is a fault to report. To use another gap's landed work, it is on `main` or the gap waits for it.
2. `dev/prompts/reviewer.md` says: the reviewer's clone is not the implementor's. A ref visible to the reviewer does not disprove the implementor's statement about its own clone, and such a statement is not a finding.
3. The two recorded shapes of lesson-8 that came from this misunderstanding (`seen-lesson-8-4aac4cae`, `seen-lesson-8-52caf205`) no longer teach it: wherever the applied lessons are kept, they are removed or reworded, with the reason.
4. A unit test holds that the implementor prompt states this and that `publish` still removes the remote.

## Files to touch
`dev/prompts/implementor.md`, `dev/prompts/reviewer.md`, the knowledge file holding the two shapes, a test.

## Risks
- Do not keep the remote in implementor clones: removing it is what keeps host paths out of the container.
- lesson-8 itself stands: only these two shapes are wrong.

## Acceptance tests
- the implementor prompt names the missing remote
- the reviewer prompt says its clone is not the implementor's
- `publish` removes `origin`

## Size budget
15 net lines of code outside `tests/` and `docs/`; prompts are not counted.
