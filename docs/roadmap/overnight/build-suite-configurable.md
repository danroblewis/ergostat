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

## Where it stopped

Built, round 1. 74 net lines outside `tests/` and `docs/` (`scripts/affected_tests.py` 58 with its docstring,
`dev/bin/onmain.py` +8, `dev/factory.toml` +5, `dev/README.md` +3; `agents.py` and `implement.py` net 0).

- `[suites] build` (dev/factory.toml) wraps the pytest command:
  `suite_watch.py -- affected_tests.py -- pytest -q -n 8 --dist worksteal`. The script adds the selected files, or
  `--collect-only`, and replaces itself with pytest (`execvp`), so a kill of the suite reaches pytest. It names only
  files that exist, so a deleted test file never fails the selection (risk 1). On an unreadable diff it runs the
  command as given, which is the full unit suite, and says so on stderr.
- `onmain.step()`: `build` when it is set and not blank, else `unit`. The first run, the alone triage, the run on main
  and the flake retry all use the same step. Results are keyed `build` in `suites_fast`, and `implement.py`'s
  `fast_seconds` now counts them. That is a one-word change in a file the definition did not list, made so the fast
  time stays honest. `agents.suites` deselects quarantined tests from `build` as it does from `unit`, and runs them
  beside it (risk 2).
- The queue (`queue.py`) is unchanged. It reads `[suites] unit`, `browser` and `demo` and never `build`.
- **Ready to delete:** the stopgap `[suites] unit` override (the shell selector) in the instance's
  `factory.local.toml`. Note that a `build` key set there overrides this one key by key, and so does `build = ""`.

Choices made alone (the reversible ones), and limits a reviewer may raise:
- The diff is `main...HEAD` against the clone's local `main`, as the definition says. If a branch has merged a newer
  main, the diff also includes main's changes. That runs more tests, never fewer.
- Changes to `dev/bin/*.py`, `tests/conftest.py` or other test helpers select nothing, so only collection runs. The
  definition maps only `ergostat/**` modules and test files. The merge queue's full run still covers them.
- Inside the suite container, git may refuse the mounted work as "dubious ownership". That shows as an unreadable
  diff, so the full suite runs (fail-safe, but the saving is lost). Not checked here: no Docker in this clone.
- The small set keeps `-n 8`, the same as the full suite, so its fallback is exactly the `unit` command. pytest-xdist
  does not distribute `--collect-only`.

Tests (tests/test_factory.py): the five acceptance tests by name, plus
`test_build_set_is_the_implementors_step_with_its_quarantine_and_triage` (quarantine deselected under `build`, a
flake retried on the small set) and `test_the_shipped_build_setting_runs_the_small_set`. Broken to watch them fail:
dropping the `isfile` filter, an unreadable diff read as empty, `build` not mapped to unit's deselection, and
`build = ""` taken as set. Each failed its test, and the code was restored. The merge-queue test also passes on main:
it guards against regression, and nothing in this branch changes the queue.
Not run: the script by hand against this repository (the command was refused), and the unit and browser suites in
full (left to the factory, as the brief says). `ruff check dev/bin` reports B023 in plan.py and E501 in review.py.
Both files are untouched here and already on main.

### After round 1's fast suites

The factory's `unit` run stopped early: about 60 tests passed, one skipped, then nothing. No test failed, no summary
line was printed, and no watchdog message appeared in the tail. That is the same early stop with no failure named that
reviews of implementors-can-run-the-four (rounds 5, 6, 8, 9), manager-sessions and a-queue-run-that-lands-nothing
also reported. Their reviews call its cause unproven. The tail also shows `bringing up nodes...` twice.

I read through the branch looking for a cause and found none. The new tests run `affected_tests.py` only as a
subprocess, never in-process, so its `execvp` cannot replace an xdist worker. The fixture factories set
`FACTORY_CONFIG` to their own `factory.toml`, which has no `build`, so no test runs the shipped `build` command (no
nested pytest). The fixture repositories use `git -C <tmp>` and an identity of their own. One hardening, on reading
only: the helper now strips `GIT_*` variables from the script's environment, so an inherited `GIT_DIR` cannot point
its git at `/work`. That is not a proven fix.

Not run: the Bash tool was refused at its first call (`git log --oneline -4 && git diff main...HEAD --stat && ...`).
So pytest and ruff were not run in this round. `git commit` was allowed later. If the next unit run stops the same way, the stop is not this branch's (lesson-13). It should be its own gap.

### Round 2: main merged, round 1's findings answered

78 net lines outside `tests/` and `docs/` (onmain.py +11, dev/README.md +4, factory.toml +5, affected_tests.py 58,
agents.py 0; implement.py is now as on main).

The merge of main (07f9b250) conflicted in three files. Main's fast suites became ruff, unit and the four browser files
(`onmain.FAST`, `AGAIN`). The resolution keeps both:
- `onmain.fast(cfg)` is `("ruff", step(cfg), "browser")`. `step` is `build` when that is set and not blank, else
  `unit`. The first run and the flake retry both use it.
- `AGAIN` maps `build` to `alone`, as it maps `unit`, so the alone run, the run on main and manage.py's reapprove
  treat a `build` failure the same as a `unit` one (DoD 4).
- `FAST` lists `build` too, so implement.py's `fast_seconds` (main's line, now taken as is) counts it.
- `room` takes main's "the failed suite's time" and falls back to `build` when `unit` is absent.
- The README paragraph names main's browser files and the `build` setting together.

Round 1's review findings, one by one (lesson-12):
- Not run by the reviewer (Bash refused). In this round I ran all of tests/test_factory.py (133 passed, 2 skipped:
  both need Docker and the agent image, and neither is this gap's) and all of tests/test_factory_manager.py
  (33 passed). `ruff check ergostat tests scripts` is clean. The unit and browser suites in full are left to the
  factory and the queue (lesson-7).
- dev/bin and test-helper changes select nothing: **unchanged.** The definition maps only `ergostat/**` and test files.
  Mapping dev/bin to tests/test_factory.py is wider than asked and would belong in its own gap. The queue still runs
  everything.
- Non-ASCII paths were quoted by git and dropped: **fixed** with `git -c core.quotePath=false diff`. New test:
  `test_a_non_ascii_test_file_is_selected`. It failed on the old line, I watched it fail, and it passes with the fix.
- Base `main` hard-coded while `[git] base` is configurable: **unchanged.** `--base REF` exists, and an instance with
  another base can pass it in its `[suites] build`. A wrong base fails safe: it runs the full suite and says so on
  stderr.

**Ready to delete** (DoD 5), as in round 1: the stopgap `[suites] unit` shell selector in the instance's
`factory.local.toml`.

### Round 3: main (b4639301) merged

The only finding was the conflict in tests/test_factory.py. Both sides only added tests at the end of the file:
this branch's small-set tests and main's pool-full-keeps-its-rank tests (`Slots` and its three tests). The resolution
keeps both blocks whole, with no line of either changed. Code outside tests and docs is as in round 2 (78 net lines).

Round 2's review findings (lesson-12):
- Not run by the reviewer (Bash refused). In this round, after the merge, all of tests/test_factory.py passed
  (143 passed, 2 skipped: both need Docker and the agent image, as in round 2). `ruff check ergostat tests scripts`
  is clean. The unit and browser suites in full are left to the factory and the queue.
- No one has seen affected_tests.py run inside a suite container: **still open, and not checkable here** (no Docker in
  this clone). It fails safe to the full suite. The next real round's log should show the `affected_tests:` line on
  stderr. If it shows "cannot read the diff" there instead, the likely cause is git's safe.directory check on the
  mounted work, and that fix belongs in its own gap.
- Base hard-coded to `main`, and dev/bin and test-helper changes select nothing: **unchanged**, for the reasons given
  in round 2. The review did not count either as blocking.

**Ready to delete** (DoD 5): the stopgap `[suites] unit` shell selector in the instance's `factory.local.toml`.
