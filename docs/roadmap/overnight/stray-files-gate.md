# stray-files-gate: the implementor's program refuses a build that commits scratch files

depends-on: []

Three review findings today were scratch files committed to a branch (`tests/_probe_test.py`, `.scratch/floors.py`, a
mutation script rewriting ergostat source): each cost a fix round. Checkable, so a program, not a lesson (owner: lessons
that can be checked become linters).

## Definition of done

- After a session, before the fast suites, `implement.py` lists the files the branch adds or changes against main and
  refuses (sent back into the same session's next round, uncounted as a review round, with the list) any that match the
  scratch patterns: a leading `.scratch/`, `scratch`, `tmp` or `_probe` path part, `*_probe*.py`, `*.orig`, `*.rej`, or a
  new top-level file or folder the definition's "Files to touch" does not name. The patterns are a setting
  (`[gates] scratch_patterns`).
- The reviewer's prompt drops the stray-file check (the program does it).

## Acceptance tests

- `tests/test_factory.py::test_a_committed_scratch_file_is_refused_before_the_suites`
- `tests/test_factory.py::test_a_new_top_level_file_not_in_the_definition_is_refused`

## Size budget

60 net lines of code outside `tests/` and `docs/`.
