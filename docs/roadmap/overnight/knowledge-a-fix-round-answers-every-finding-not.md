# knowledge-a-fix-round-answers-every-finding-not: a new lesson, § 12

depends-on: []

Branch `knowledge-a-fix-round-answers-every-finding-not`, from main. Asked by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: a new lesson, § 12, as below, and nothing else changed.

## 12. A fix round answers every finding, not only the blocking ones
Seen as: warm2: two non-blocking findings of round 1 (a stale SPEC sentence, a traceback on a bad --check-warm file) ignored in the fix round, then blocking in round 2, parking the gap.
**Check:** list every finding of the review you are answering, blocking and not, and for each say in the report what changed or why it stays; a non-blocking finding left unanswered becomes blocking in the next round

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).

## Where it stopped

Built: the lesson is appended to `dev/knowledge/review-lessons.md` word for word, final period omitted as given.
One choice made without anyone to ask: "nothing else changed" could not hold to the letter. Three assertions in
`tests/test_factory_knowledge.py` hard-code the lesson count. Two compare against `lesson-1`..`lesson-11` (in
`test_knowledge_files_parse`, the acceptance test, and in `test_brief_carries_knowledge_within_budget`). One expects
`lesson.py add` to number the next lesson § 12 (`test_cli_tools_on_a_fixture_instance`). With § 12 added, all three
fail. They now count to 12 and expect § 13. This is the smallest change that lets the lesson exist, and it is easy to
undo; no code outside `tests/` changed. Nothing is left.
