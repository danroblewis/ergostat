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

## Where it stopped

Round 1 stopped before any code, because a gap this one depends on is not on main. `depends-on` names
`code-health-simplifier`, and the brief lists it as merged, but this clone (main at 900f8aa6, every ref and the whole
history: `git log --all --diff-filter=A`) has none of what it makes:

- no `scripts/code_evidence.py`, though point 1 says every reading is computed from it ("no second implementation");
- no `dev/model/code-health.yaml`, the file where point 1 puts the five auxiliaries and their sensors;
- no `simplify-when` block or `drift` input (point 3), and no simplifier pool of 1;
- no `docs/roadmap/overnight/code-health.md`, the parent definition.

`code-health-coverage` is on main (`scripts/coverage_report.py`, `tests/coverage_lines.py`), so the `code-coverage`
reading alone could be built. Building it alone would put a partial gap on main. Writing the evidence script, the
model file or the simplifier here would build another gap inside this one (the brief's rule 1, lesson-13). I took the
reversible option and built nothing.

Left: all five points and all four acceptance tests. Once `code-health-simplifier` has really merged into main,
continue this branch with main merged in. The definition above stays as it is.
