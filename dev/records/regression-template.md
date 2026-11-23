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

## Where it stopped

Built, round 1: all four done items, the four named tests plus `test_each_part_is_opt_in`; 150 net lines outside
tests/docs/dev (68 template, 82 reader). Choices made alone, each the reversible one:

- `once: true`, like `interventions` and `repair`, so the goals keep the names written here (`tests-green`,
  `claims-kept`, `changes-hold`) and repair's `fixes-hold` is named plainly. A second use is `used-twice`.
- Opt-in: each part is made only when its parameter is given: `every` (passing counts), `block` (escapes; `escape-share`
  defaults to 0.1), `changes: true`, `repair: NAME`. No `with:` makes nothing.
- The reader loads the model from its folder and runs `claims.tests` itself (its `in:`, with `ERGOSTAT_ROOT`, as the
  claim check does), so the command is the one declared, never a copy in `with:`. It gives no value (exit 1) when: no
  command, a model that does not load, past `min(claim timeout, 0.9 × timeout)` (the run's whole process group killed),
  no summary, a summary where nothing ran (only skipped or deselected, "no tests ran"), or a non-zero exit with no
  failure counted. Failing = failed + errors.
- Feedback: a person block may not `out:` an auxiliary, since that adds a `set` sensor on no clock, and then the
  auxiliary is never stale (found while building; the stale test fails that way). Each person block instead moves a
  flow of fixes into a cumulative stock, and the auxiliary is `driven-by: -flow.<fixes>`, so the loop closes the long way.
- `on-stale: "off"` on all three goals, not only `tests-green`: a reading that stops is counted as off.
- `repair: NAME`: repair is `once`, so the name only turns the part on; a person block `fixes-reviewer` serves
  `fixes-hold` beside `repair-settle` (out: repair's `flow.fixes-reverted`). Nothing of repair's is made again.
- `agent:` is a name put on every person block (left out when not given); `every` is at least 1m, `timeout` 10s to 6h.
- While stale, the engine keeps `status` as it was and sets `goal.tests-green.off` to 1 (SPEC §9.6). The test pins the
  off signal, the `ergostat.goal.stale` event, the person block's input saying `off`, and the person being asked.

Not run here: the unit suite as a whole, the four browser files and demo_check (no example touched; no page changed).
