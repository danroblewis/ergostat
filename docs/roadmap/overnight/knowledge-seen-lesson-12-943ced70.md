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

Round 1, second report: `unit` failed again, and its tail is cut off the same way: passing dots, then nothing. pytest
always prints a summary line when it ends, even on failure, and `fac.suite` (dev/bin/fac.py:376) sets no timeout. So
something outside pytest killed the run. Possible killers: the suite container's limits (dev/bin/agents.py:48:
`--memory 12g`, `--pids-limit 4096`) or `suite_watch`'s 6 GB / 1,500-thread watchdog. Run alone again here,
`tests/test_factory_knowledge.py` gave 34 passed, and `ruff check ergostat tests scripts` is clean. The branch diff
against main is still just `dev/knowledge/review-lessons.md` (+3/-1) and this file. Following lesson-13, I changed no
code or tests. What is left is outside this gap: find out why the `unit` container is being killed (its exit code
and the watchdog's log will show which limit) in its own gap, then run `unit` again on this branch.

Round 2: there were no review findings to answer. The branch already holds main (8dcc6e97), and the diff against main
is still only `dev/knowledge/review-lessons.md` (+3/-1) and this file. Run again after the merge:
`tests/test_factory_knowledge.py` gave 34 passed, and `ruff check ergostat tests scripts` is clean. Following
lesson-13, I changed no code or tests. What is left is the factory's `unit` run on this branch under the watchdog. If
it is cut off again, finding out why its container is killed belongs in its own gap.
