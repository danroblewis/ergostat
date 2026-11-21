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
