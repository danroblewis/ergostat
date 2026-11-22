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

## Where it stopped

Built, round 1. Every point is done; 8 net lines of code (`dev/bin/knowledge.py`, +11 -3), within the 15.

1. `dev/prompts/implementor.md`, under *The gap*: the clone has no remote by design, `origin/*` does not exist,
   local `{base}` is the base as of the clone (and is what to merge and compare with where a rule says
   `origin/{base}`), other gaps' branches are absent, neither is a fault, and another gap's landed work is on
   `{base}` or the gap waits for it.
2. `dev/prompts/reviewer.md`, under *The branch*: the reviewer's clone is not the implementor's; a ref visible to the
   reviewer does not disprove the implementor's statement about its own clone, and such a statement is not a finding.
3. The two shapes are in no tracked file: they are applied `lesson` items in the instance's record, which this
   clone cannot reach, and `lesson.py retire` removes a whole lesson, not one shape. So `dev/bin/knowledge.py`
   gains `WITHDRAWN`, an allowlist of the two item ids, each with its reason, and `applied()` skips them. Briefs
   (`knowledge.block`) and the collector (`knowledge.py sync`) both read through `applied()`, so neither carries them.
   lesson-8 and its other shapes stay. This is the most reversible option: the record is left as it is (a line taken
   out of `WITHDRAWN` brings a shape back), and because the items stay `applied` there, the librarian, which skips
   an id it already holds, does not propose the same shape again.
   Not checked: which of the record's lesson-8 shapes each id is. The shape texts are not in this clone, and the
   command that would have hashed the candidate texts as the librarian does was refused. Both reasons are worded to
   hold for any of the no-remote shapes.
4. `tests/test_agents.py::test_the_implementor_is_told_its_clone_has_no_remote` (a real git clone: `publish` pushes,
   then leaves no remote and no remote refs; both prompts say what points 1 and 2 ask) and
   `tests/test_factory_knowledge.py::test_the_no_remote_shapes_of_lesson_8_are_not_carried`. I broke each guard and
   watched its test fail: with the `git remote remove origin` line taken out of `publish`, the first test fails; with
   the `WITHDRAWN` check taken out of `applied()`, the second fails.

Run: both test files in full (17 and 77 passed) and ruff (clean). Not run: the unit suite and the four browser files
(the factory and the queue run them). Main was not merged in: this clone has no remote, and local `main` is the base.
