# knowledge-seen-lesson-12-943ced70: lesson-12 seen as a new shape

depends-on: []

Branch `knowledge-seen-lesson-12-943ced70`, from main. Asked by the librarian, approved by the coordinator.

## Definition of done

`dev/knowledge/review-lessons.md`: lesson-12 seen as a new shape, as below, and nothing else changed.

Add to its "Seen as:" (a new line under its first paragraph if it has none), in its style: the blocking stray-file finding was answered in rounds 2 and 3 by rewording a comment (c234835d) instead of removing the file, so it stays committed across rounds

From:

> tests/test_probe_tmp.py:1: the stray scratch file named as blocking in rounds 1-3 is still committed (added in 69e04cdb; c234835d only reworded its comment to 'committed by mistake... Remove it before merge'). A stray file would reach main, which people install from. Fix: one commit with `git rm tests/test_probe_tmp.py`, made by whoever has delete rights (the last two fix rounds were refused git rm).

## Acceptance tests

- `tests/test_factory_knowledge.py::test_knowledge_files_parse`: the knowledge files still parse into entries with ids.

## Size budget

0 net lines of code (knowledge only).
