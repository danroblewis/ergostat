# build-suite-configurable: the implementor's loop runs a small configurable test set; the full suites run only in the merge queue

depends-on: []

The owner (2026-11-21): "We only want to run a minimum set of specific tests during the implementors loop, and we want to run the full suite on a combined merge queue", and "We might want to bring back a per-build test suite later, if it could be configurable or commented out". After each session `onmain.check` runs the whole unit suite on the branch (about 530 s on 4 CPUs), which used 12.7 of 22 busy cores. The instance has a stopgap in `factory.local.toml`: a shell selector inside `[suites] unit`, which applies only inside the suite container. Replace it with a real setting.

## Definition of done
1. `[suites] build` in `dev/factory.toml` is the command for the implementor's post-session test step (`onmain.check`, including its flake retry). It defaults to the small set. Commenting it out, or leaving it empty, runs the full `unit` suite there, as before; a comment beside it says so.
2. The small set is computed by a program in the repository, `scripts/affected_tests.py`: the test files the branch changed (`main...HEAD`), plus `tests/test_<module>.py` for each changed `ergostat/**/<module>.py` that has one. With none, it checks that the tests collect (`--collect-only`). If it cannot read the diff, it runs the full `unit` suite (lesson-3: never a silent pass).
3. The merge queue always runs `unit`, `browser` and `demo` in full and never reads `build`.
4. Failure triage (`alone`, the run on main, flake retry) works the same on the small set.
5. The stopgap `unit` override in the instance's `factory.local.toml` is named in *Where it stopped* as ready to delete.

## Files to touch
`dev/factory.toml`, `dev/bin/onmain.py`, `dev/bin/agents.py`, `scripts/affected_tests.py`, `tests/test_factory.py`.

## Risks
- A selector whose last test file is missing must not fail the whole selection and fall through to the full suite (the stopgap's first version did).
- Quarantined tests stay deselected in both modes.

## Acceptance tests
- a branch changing a module and its test runs only those
- a docs-only branch runs collection only
- an unreadable diff runs the full suite
- `build` unset runs the full unit suite in the implementor's step
- the merge queue runs the full suites with `build` set

## Size budget
80 net lines of code outside `tests/` and `docs/`.
