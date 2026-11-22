# code-health-measures: net lines, long functions, duplication, dead code and coverage as measures, with goals on their trend

depends-on: [code-health-coverage, code-health-simplifier]

Sub-gap 5 of 5 of `code-health` (its definition: `docs/roadmap/overnight/code-health.md`). It lets the factory see the
code getting simpler. Branch `code-health-measures`, from main. It can be built in parallel with
`code-health-first-run` and `code-health-guidance`, because it reads their outputs but does not need them.

## Definition of done

1. **The measures.** `dev/bin/measure.py` gains five readings, each computed from `scripts/code_evidence.py` (no
   second implementation) on the running version's checkout:
   - `code-net-lines`: net lines of `ergostat/`, `dev/bin/` and `scripts/`;
   - `code-long-functions`: functions over 60 lines;
   - `code-duplicates`: duplicate function bodies;
   - `code-dead-candidates`: dead-code candidates;
   - `code-coverage`: the statement-weighted share, from `code-health-coverage`'s report.

   In `dev/model/code-health.yaml` each is an auxiliary with a sensor (`every: 1h`), next to the factory's other
   measures.
2. **Goals on their trend.** Each reading is stamped with main's commit `seq`. A goal holds each measure's change over
   the last 10 merges of main (by `seq`): net lines, long functions, duplicates and dead candidates not rising; coverage
   not falling. A goal that is off asks the coordinator, as the other measures' goals do.
3. **Drift fires the simplifier.** The `drift` input of `simplify-when` (from `code-health-simplifier`) reads 1 while
   any of the four size goals is off. The simplifier's pool of 1 still holds.
4. **Shown where things are shown.** The measures appear in the factory's model, so they appear in its diagrams and
   system boxes. No new page or panel.
5. `dev/README.md` lists the measures with the others.

## Files to touch

`dev/bin/measure.py`, `dev/model/code-health.yaml`, `dev/README.md`, `tests/test_code_health_measures.py` (new).

## Risks

- lesson-3: a missing checkout, a failing evidence run or no coverage report read as 0 lines or 0 duplicates, which
  would look like the best trend ever. Each one gives no value (exit 1).
- lesson-2: the trend taken over wall-clock time, so that two readings of the same main count as change. Readings are
  compared by main's `seq`, and repeated readings of one sha count once.
- lesson-8: "the code got simpler" claimed from net lines alone. The goals are per measure, and none is called
  "simpler" in the docs unless all four size measures hold.

## Acceptance tests

`tests/test_code_health_measures.py`:
- `test_measures_match_code_evidence`: on a fixture repository, each reading equals the matching sum over
  `code_evidence.py`'s rows.
- `test_missing_inputs_have_no_value`: no checkout, a failing evidence run, or no coverage report each exit 1 for the
  measures that need them (lesson-3).
- `test_trend_by_seq_counts_one_sha_once`: three readings of one sha and one of the next give a change of one step, not
  three (lesson-2).
- `test_drift_turns_simplify_when_on`: a rising `code-net-lines` over 10 merges turns the size goal off and sets
  `simplify-when`'s drift input to 1, and nothing fires while a simplification gap is in flight.
- `ergostat check` on the root model reports no errors. The unit suite and the four browser files, rc 0, ruff clean.

## Size budget

50 net lines of code outside `tests/`, `docs/` and `dev/`, where any is needed at all (the measures are factory code in
`dev/`).
