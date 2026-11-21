# stray-patterns-from-evidence: The stray-file gate catches the strays that really happened

depends-on: [implementors-can-clean-up]

Audit 2026-11-21 replayed tonight's 8 real strays: the gate caught 3 without a "Files to touch" section and 5 with one. `tests/test_zz_scratch.py`, `tests/test_zz_profile_tmp.py` and `operating-states.md.tail` pass, and the reviewer's own stray check was removed. It also refuses a `*_probe.py` the definition explicitly names.

## Definition of done
The gate catches all 8, as a fixture. A file the definition names is never refused. A new file outside the definition's "Files to touch" is shown to the reviewer even when no pattern matches.

## Files to touch
`dev/bin/implement.py`, `dev/factory.toml`, `dev/prompts/reviewer.md`, `tests/test_factory.py`.

## Risks
- lesson-9: the fixture is the real list of strays.

## Acceptance tests
- `tests/test_factory.py::test_the_gate_catches_the_eight_real_strays`
- `tests/test_factory.py::test_a_file_the_definition_names_is_not_refused`

## Size budget
30 net lines of code outside `tests/` and `docs/`.

## Where it stopped

Built, round 1 (20 net lines: implement.py +9, review.py +2, factory.toml +2, reviewer.md +7). Choices made with nobody
to ask, each the most reversible reading:

- **The fixture's list.** The audit's own list is not in this clone. Seven strays are on the record (review findings
  and their removal commits): `tests/test_zz_scratch.py`, `tests/test_zz_profile_tmp.py`, `operating-states.md.tail`,
  `scratch_probe.py`, `.bench/test_bench_detach.py`, `.mut/mut.py`, `tests/test_probe_tmp.py`. The eighth is taken to
  be `tests/_probe_test.py`, the finding the stray-files gate was built from: it fits the audit's counts (3 caught
  without Files to touch, 5 with). `operating-states.md.tail` is taken to sit beside its definition, under
  `docs/roadmap/overnight/` (it passed with Files to touch, so it was under a folder main has). If the real eighth is
  another file, change `REAL_STRAYS` in tests/test_factory.py and add a pattern if it needs one.
- **New patterns** (`[gates] scratch_patterns` and the default): `test_zz*`, `*_tmp.py`, `*.tail`, `.bench*`, `.mut*`.
  Each matches path parts, as before. The gate now catches all 8 with or without a Files to touch section.
- **A named file is never refused.** "Named" means the path, or a folder above it, appears under Files to touch
  (brief.files_of). A one-level folder such as `.bench/` does not fit files_of's path pattern, so it does not count as
  named. That rule lives in brief.py, which this gap does not touch.
- **Shown to the reviewer: one change outside Files to touch.** The reviewer's brief is assembled in
  `dev/bin/review.py`, so it gained 2 lines that pass `implement.unlisted` (the new files the definition does not name)
  to `{unlisted}` in reviewer.md. Without that the prompt could not show them. reviewer.md again tells the reviewer to
  judge each listed file and to block on a stray. With no Files to touch section, every new file is listed (worst
  case). The branch's own definition file is listed too; hiding it would need the branch name inside unlisted().

## Where it stopped

The factory reported `unit` failed, but the tail it gave has no FAILED or ERROR line and no summary: it ends in the
middle of a line of dots, which reads as a run cut off (killed or timed out), not a failing test. Re-run here, a group
of files at a time: tests/test_factory.py (118 passed, 2 skipped); the files that touch the factory, its reviewer, its
prompts or factory.toml (test_factory_manager, _knowledge, _resources, _sessions, test_improve, test_modelreview,
test_recipes, test_interventions: 214 passed; test_review, test_factory_join, test_gate, test_templates, test_churn,
test_churn_carry, test_agents_page, test_goal_per, test_inbox: 146 passed, 1 skipped; test_code_health_coverage: 11
passed). None failed, so no code changed in this round. The watched suite (`uv run python scripts/suite_watch.py --
uv run python -m pytest -q -n 8 --dist worksteal`) was refused in this session, so the whole unit suite was not run
here. What is left: the factory's next unit run; if it fails again with a named test, that test.

## Where it stopped

The factory reported `unit` failed a second time with the same kind of tail: dots cut off near 59%, with no FAILED,
ERROR or summary line. This time the watched suite ran here, the factory's own `[suites] unit` command
(`uv run python scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal`) at this head (288e20a4):
2498 passed, 69 skipped, 1 xfailed in 553.68s, rc 0. The watchdog killed nothing (peak 393 threads, 1678.5 MB RSS, 174
processes, nothing left behind). `uv run ruff check ergostat tests scripts` is clean. The suite's limit is 3600s
(agents.py TIMEOUTS["suite"]), so this is not a timeout at this length. The likeliest cause is that the factory's suite
container was stopped from outside (its machine-wide slot or the container's own limits), not a test this branch
breaks. No code changed, since no test fails. What is left: the factory's next unit run, and if a run is cut off
again, the reason from the suite runner's side (the container's exit, the slot's log). That is outside this gap.

## Where it stopped

Round 2: main (e1e778c1) merged in. The conflict in `dev/bin/implement.py` was in `strays()`. The fix keeps the
branch's `unlisted()` (which filters out files main has) and main's addition of `fac.DEFS`'s top folder (`dev/`, now
where definitions are written) to the folders that count as known. Main's recursive ls-tree for `tops` gives the same
top-level names as the branch's plain one, so the branch's form is kept. Because main moved definitions to
`dev/records/`, `test_a_file_the_definition_names_is_not_refused` now expects `dev/records/alpha-thing.md` (the gap's
own definition, still shown to the reviewer) instead of the old path. After the merge, tests/test_factory.py ran 127
passed, 2 skipped and 1 failed (that test, at the old path). After the fix, both acceptance tests pass. `uv run ruff
check ergostat tests scripts` is clean. Not run here: the whole unit suite and the browser files (the factory runs them).
