# knowledge-seen-lesson-7-037d2f0a: lesson-7 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-7-037d2f0a`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-7 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: the gap's HEAD carries another branch's merges (backlog) that origin/main lacks, so landing it ships the whole backlog feature

From:

> Scope / lesson-7: HEAD contains 2b101c6 'Merge branch backlog' (and 67c673e, 600535d, ff49649, d61e27e), which origin/main (f7b93be) does not; merge-base is 05c6dc9. Landing factory/flake-quarantine lands the whole backlog feature (dev/bin/backlog.py, solve.py, intake.py, ergostat/leases/ready.py, dispatch.py, compile.py, numbers/eta*.py, precedence.py, web/static/*, docs/SPEC.md, tests/test_backlog.py, test_take_order.py), outside this definition. Rebase the gap's four commits (53df798..070b797) onto origin/main, or land backlog first.

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).
