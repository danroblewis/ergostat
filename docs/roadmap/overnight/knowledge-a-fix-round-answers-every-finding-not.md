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

After the fast suites: `unit` came back as failed, but its log names no failing test. It stops at 79% with no
`FAILED`/`ERROR` line, and `scripts/suite_watch.py` never printed its closing JSON summary, which it prints on every
exit, even after killing for limits. Something outside the suite killed the runner (the container or the run was
stopped); no test failed. This branch changes no code, only one markdown file and the three expected counts above,
so nothing in the code was changed in answer. `tests/test_factory_knowledge.py` passes alone (20 passed). The suite
needs to run again; if it stops at the same place, the cause is outside this branch.

### Round 2

The queue's unit failures (`test_cli_fallback.py::test_an_engine_running_takes_event_add_from_a_run_while_the_yaml_is_broken`
and three in `test_templates.py`) are not this branch's: it changes no code. They come from the suite inheriting the
merge-queue engine's `ERGOSTAT_*` variables, which main fixed after this branch was cut (323dc04, merged as f4afd1c:
`tests/conftest.py` drops them per test, `dev/bin/fac.py` drops them from the suite's environment). All four pass here
alone in a plain shell (4 passed). Not done: merging main into this branch. `git merge` was refused by this session's
permissions, and working around that would go against what was refused. The factory needs to merge origin/main
in and run the suites again before this is called built (lesson 7).

Every round-1 finding, answered:
- Lines 80-81 longer than 120 characters: wrapped at 120, no words changed.
- No final period on the Check: added, so § 12 ends like every other Check. A choice made without anyone to ask,
  and easy to undo. The definition's text reads as one sentence cut off, not a deliberate omission.
- No one-line description of the class before "Seen as:": stays. The definition gives the entry's text and says
  nothing else changes. The heading already names the class. A general line is for the definition's author to add.
- The round-1 note above says `suite_watch.py` prints its summary "on every exit". That is wider than the code.
  `scripts/suite_watch.py:119` catches only `KeyboardInterrupt` (raised on SIGTERM), so a SIGKILL of the watcher or
  any other exception exits without the summary. The narrower claim holds: a missing summary means the watcher
  itself ended abnormally, so no test result is missing from its log. The queue's run later named real failures,
  and the paragraph above traces them to the inherited environment.

Tests: `tests/test_factory_knowledge.py` 20 passed; the four queue failures 4 passed alone; ruff clean.
