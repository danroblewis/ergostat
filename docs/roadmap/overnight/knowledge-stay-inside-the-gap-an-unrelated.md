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
