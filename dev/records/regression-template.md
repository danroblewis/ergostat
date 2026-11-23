# regression-template: A library template, regressions, that gives a user's model passing counts, escapes and regressed fixes

depends-on: [regression-fixes-hold-goal]

## Problem

Ergostat adds nothing of its own accord (CLAUDE.md:52-53), so a user gets regression guarantees only by asking. There is no template to ask for (proposal section 6b; milestone gap 7).

## Change

A template ergostat/library/templates/regressions/template.yaml, used as `uses: {regressions: {use: regressions, with: {...}}}` (the way the factory uses `interventions`):
- **Passing counts**: an auxiliary `tests-failing` whose sensor runs the model's declared `claims: tests` command (docs/SPEC.md:5236) on a schedule (`every` parameter) through a small reader, `python -m ergostat.regressions counts`. The reader gets a pytest-style summary parser in ergostat/regressions.py. A run that cannot be read, or has no summary, gives no value. Goal `tests-green`: `<= 0`, `on-stale: "off"`.
- **Escapes**: an auxiliary on `builtin: ergostat.trust.contradicted@${block}` (docs/SPEC.md:5299-5309), goal `claims-kept` `<= ${escape-share}`.
- **Regressed model changes**: `builtin: ergostat.model.regressed` (docs/SPEC.md:5187), goal `changes-hold` `<= 0`.
- **Regressed fixes**: when the model also uses `repair`, a parameter names its instance and the template reads `fixes-hold`. It does not duplicate it.
- Every goal is served by a `person` block by default (rung 0), with the agent as a parameter.
The parser is tested on its own. Flakes and quarantine are left out: they need a user's own item kind.

## Definition of done

1. A model using the template checks clean, with no missing feedback.
2. A failing test run turns `tests-green` off.
3. An unreadable command leaves it stale and off, never holding.
4. Each part is opt-in through `with:`.

## Files to touch

ergostat/library/templates/regressions/template.yaml (new), ergostat/regressions.py (new), tests/test_regressions_template.py (new).

## Acceptance tests

- `test_the_template_checks_clean`
- `test_a_failing_run_sets_tests_green_off`
- `test_an_unreadable_test_command_is_stale_and_off`
- `test_counts_parser_forms` (passed, failed, errors, none)

## Size budget

150 net lines outside tests/ (the template YAML and the reader).

Area: regression. The second wave, planned 2026-11-22 from landed proposals and the owner's open asks.
