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

## Where it stopped

Built, round 1 (46 net lines: implement.py +36, fac.py's stand-in +7, factory.toml +3). Choices made with nobody to
ask, each the most reversible reading, each a setting or one line to change:

- **A file already on main is never refused.** main has `scripts/scale_probe.py`, which `*_probe*.py` matches; refusing
  a branch for changing it would block real work. So "adds or changes" is checked on paths main does not have.
- **The patterns are globs matched against every path part** (`fnmatch`), defaults `.scratch*`, `scratch*`, `tmp*`,
  `_probe*`, `*_probe*.py`, `*.orig`, `*.rej`. A setting that is not a list of strings stops the build (fails closed).
- **The top-level rule is applied only when the definition has a "Files to touch" section.** Without one there is
  nothing to compare against (this definition has none, nor do hand-written ones like it). A top-level name counts as
  named when any path under Files to touch starts with it.
- **A refusal uses one of the run's `[ai] suite_fix_rounds` sessions** (the suites do not run for it), and is not a
  review round or a failed gate. If the files are still there after the last session, the run counts as one failed
  build (`build_failures`, the existing kill rule), so a session that never removes them cannot loop forever.
- The free stand-in gained `FACTORY_STANDIN_WRITES` for the tests. The fixture plans (the planner stand-in's and
  test_factory_knowledge.py's) now name `standin/work.txt`, the stand-in implementor's note, as a real plan would.
