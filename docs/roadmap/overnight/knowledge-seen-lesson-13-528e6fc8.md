# knowledge-seen-lesson-13-528e6fc8: lesson-13 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-13-528e6fc8`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-13 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: a scratch mutation script that rewrites ergostat source, committed to the branch outside the gap and counted against the size limit

From:

> .mut/mut.py (added in 1e563e30, still in `git diff origin/main...HEAD` at b78fa9b0): a scratch mutation script that rewrites ergostat source files, whose docstring says '(Not committed.)'. It is a stray file headed for an installable main, and its 55 lines are the whole size overrun (316 against 300; about 261 without it). Raised for the fifth round: the factory or the owner must run `git rm .mut/mut.py && git commit`; no other change is needed.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).
