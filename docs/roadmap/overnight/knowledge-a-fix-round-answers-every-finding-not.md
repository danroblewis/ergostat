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
