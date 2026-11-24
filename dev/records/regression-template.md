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

Round 2, answering the one finding (the test run orphaned when the sensor's own timeout fires first):

- The deadline is counted from the reader's start (`BEGAN`, taken when the module loads), less a fixed margin of
  `max(2s, 5% of --within)`, not 0.9 × timeout counted from the run's start. At the 10s minimum the run gets about 8s
  less the reader's own load time.
- The margin alone cannot be enough (a loaded machine can start the reader late), so both ways the sensor's timeout
  can land now stop the run. The engine's `subprocess.run` kills only the shell's pid. (1) When the shell forks the
  reader (this container's `sh`), the reader is orphaned: it waits on the run in 0.2s steps and, once its parent pid
  changes, kills the run's process group. (2) When the shell execs the reader (bash, `exec`), the reader itself is
  killed: a guard child forked beside the run waits on a pipe from the reader and kills the run's group on EOF with
  nothing written. The reader writes one byte once the run has ended and been reaped, so the guard never signals a
  group after it is gone (lesson-11). Left open: a window of a few instructions between `Popen` and the fork of
  the guard, where a reader killed there leaves the run going. The engine killing a sensor's whole group (it starts
  each in its own session) would close that window and fix it for every sensor, but it is outside this gap (lesson-13).
- Test `test_the_sensor_timing_out_first_leaves_no_test_run`, run both ways (forking shell, and `exec`): the sensor's
  timeout (3s) fires long before `--within 300`, and the test command's pid, which it writes, is shown gone (a zombie
  counts as gone). Seen to fail: with the parent-pid check removed the forking case fails; with the guard's kill
  removed the `exec` case fails. `test_the_reader_counts_its_deadline_from_its_own_start` pins the margin. The
  existing past-its-time test now also shows the killed run's pid gone.
- Size: 179 net lines outside tests/docs/dev (68 template, 111 reader).
Overrun reason: 29 lines over the 150 budget, all for the round-2 finding: the guard child (16 lines) and the waiting loop that notices its shell is gone plus the deadline from the reader's start (13 lines). The template and the rest of the reader are unchanged, and both kill paths are needed, since a POSIX shell may fork the reader or exec it.

Run here: tests/test_regressions_template.py (18 passed) and ruff (clean). Not run: the unit suite as a whole, the four
browser files and demo_check (no example touched; no page changed).
