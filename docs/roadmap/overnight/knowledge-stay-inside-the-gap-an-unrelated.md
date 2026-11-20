# knowledge-stay-inside-the-gap-an-unrelated: a new lesson, § 13

depends-on: []

Branch `knowledge-stay-inside-the-gap-an-unrelated`, from main. Asked by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: a new lesson, § 13, as below, and nothing else changed.

## 13. Stay inside the gap: an unrelated failure is reported, not fixed in the branch
Seen as: continue-branch: a lease-renewal test failed under load; the implementor wrote its own lease fix into the branch, and the review failed the gap on it.
**Check:** when a suite fails on something your change did not touch, name the test and why it is unrelated in your report and stop there; a fix outside the definition of done belongs in its own gap

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).

## Where it stopped

Built. The lesson is in `dev/knowledge/review-lessons.md` as § 13, word for word. The two long lines are wrapped at
120 characters like the rest of the file. The Check line has no final period because the definition gives it without
one, and I kept the text exactly as given.

Choice made without anyone to ask: "nothing else changed" could not hold with green tests. `tests/test_factory_knowledge.py`
hard-codes the lesson count in three places, which the review of § 12 also found: lines 107 and 129
(`range(1, 13)` → `range(1, 14)`) and line 325 (the next lesson made by `lesson.py add` is `## 14.`, not `## 13.`).
Line 107 is in the named acceptance test, so it could not pass without the change. I made the smallest edit that
keeps the suite green: three numbers, no other test changes. These failures come from this change, so fixing them
here does not break § 13. Taking the count from the file's headings instead would stop this from happening again;
that belongs in a separate gap and is not built here.

Not done: merging origin/main into the branch and running the suites again. This session's permissions refused
`git merge`, so the factory has to do the merge and the re-run.

The fast suites after the build: `unit` was reported as failed, but its tail names no failing test. It stops partway
through the progress dots, with no pytest summary, no `suite_watch` JSON line, and no watchdog "killing" message. So
the run was cut off from outside, not failed by a test. The branch changes no code: one knowledge file, three numbers in
`tests/test_factory_knowledge.py`, and this file. `tests/test_factory_knowledge.py` passes alone (20 passed). It is the
only test file that reads the knowledge files (checked by grep for `knowledge` and `lesson` in `tests/`). Ruff is clean.
Following § 13, I changed nothing outside the definition: there was no failure to fix. Left for the factory: run `unit`
again to the end, then the merge of main and the re-run noted above.
