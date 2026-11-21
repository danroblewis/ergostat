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

## Where it stopped

The edit is built (37c80c63): lesson-12's "Seen as:" line in `dev/knowledge/review-lessons.md` gains the
redesign-rescored-as-the-record-moves shape, and that is the only file it changes besides this one.
`tests/test_factory_knowledge.py` passes (34 passed, run alone), and it is the only test file that reads
`dev/knowledge/`.

The factory's `unit` suite was reported failed, but the tail it gave holds no failing test, error or traceback: it stops
partway through a line of passing dots, so it reads like a run that was killed or cut off, not a test that failed. This
branch changes no code and no tests, so no code here could have caused it. Following lesson-13, I changed nothing to
"fix" it. The reversible option is to run `unit` again under the watchdog. If it fails again, the failing test's name
belongs in its own gap.
