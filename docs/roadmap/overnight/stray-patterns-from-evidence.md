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
