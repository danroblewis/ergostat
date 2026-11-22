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

### Round 2: built

**Round 1's reason was wrong.** The review was right: it said "every ref and the whole history" more broadly than the
clone supported. The simplifier had merged. This clone's `main` is b4639301 (this clone has no `origin` remote), and
2c28fe98 merged it into the branch. That main has `scripts/code_evidence.py`, `dev/model/code-health.yaml`,
`simplify-when` and `dev/bin/simplify.py`. `docs/roadmap/overnight/code-health.md` (the parent) is still not in it.
That file is only background, so nothing waits on it.

**What was built, point by point:**

1. `dev/bin/measure.py` adds `code-net-lines`, `code-long-functions`, `code-duplicates` and `code-dead-candidates`. Each
   is a sum over the rows `scripts/code_evidence.py` prints (run as a subprocess at main's sha, resolved first). It adds
   `code-coverage` too: covered over statements, from the report `coverage_report` already chooses.
   `coverage_report` was split so it also returns that report's seq, sha and modules (`latest_coverage`). Each is an
   auxiliary in `dev/model/code-health.yaml` with a sensor, `every: 1h`.
2. Each reading is appended to `run/code-measures.jsonl` with the seq and sha it measured. For `code-coverage` that is
   the report's own seq and sha. `measure.py NAME-change` gives the change over main's last 10 merges, by seq. A sha
   counts once (its last reading), and a sha no longer on main is skipped. The five `-change` auxiliaries carry the
   goals `code-*-not-rising` (`<= 0`) and `code-coverage-not-falling` (`>= 0`). A goal can only hold an auxiliary or a
   stock, so the change needs an auxiliary of its own. That makes five more auxiliaries than point 1 names. This is the
   reversible reading: deleting them and the goals undoes it. `code-health-off` (an expr) feeds
   `block.improve-factory`, which is the coordinator `factory-off` asks. That keeps `measures.yaml` untouched.
3. `code-drift` is the max of the four size goals' `.off`. It is `simplify-when`'s `drift` input, and the expression is
   now `max(days >= 3, drift) * (inflight < 1) * (1 - over)`. Pool 1 is unchanged, both in the expression and in
   `simplify.py`.
4. The five measures are in the `code-health` system's `show:`. There is no new page.
5. `dev/README.md` has a "code measures" paragraph in the simplifier section. It does not call the code "simpler".

**Outside the listed files:** `tests/test_code_health_simplifier.py`'s `simplify-when` test fed the expression only
`days`, `inflight` and `over`. Its model comment said the drift input would come from this gap. The test now passes
`drift=0` by default (2 lines).

**Lesson-3:** no checkout, a module that does not parse (`code_evidence.py` exits 2), no coverage report, a report
with 0 statements, an unreadable history line, or fewer than two seqs in the window. Each gives no value (exit 1),
and nothing is stamped.

**Size:** 0 lines outside `tests/`, `docs/` and `dev/`. In `dev/`: `measure.py` +97 −5 (about 70 of it code, the rest
docstring), `code-health.yaml` +101 −3, README +12.

**Lesson-9 (each break seen to fail a test, then put back):**

- a failing evidence run read as rows: `test_missing_inputs_have_no_value` failed;
- the on-main check dropped: `test_trend_by_seq_counts_one_sha_once` failed (it read the undone sha's 500);
- each sha's first reading kept instead of its last: the same test failed (1 ≠ −1);
- `drift` left out of `simplify-when`'s expression: `test_drift_turns_simplify_when_on` failed.

**Not run:**

- `ergostat check` as a command. `uv run ergostat check` and `uv run python -m ergostat check` were both refused in
  this session. In their place, `tests/test_factory.py::test_the_factory_model_loads` passed. It does the full read of
  the root model, extremes included, and asserts no errors.
- The measures against this repository. A scratch config under `/tmp` was refused too.
- The full unit suite and the four browser files. They are left to the factory's watchdogged run.

### Round 2, sent back: "`ergostat check` said nothing readable on the branch"

I could not reproduce this, and no model change follows from it. At the branch's HEAD (main b4639301 already merged
in, and no newer main in this clone), `ergostat check --json --no-coherence`, run as `[suites] check` runs it, prints
its JSON in about 6 s. That run had stderr in the same log, and `fac.findings` parsed the output with no error in it.
The new `test_check_on_the_root_model_reports_no_errors` (in `tests/test_code_health_measures.py`) does exactly this.
I broke `code-health-off`'s `out` to an unknown block, and the test failed (bad-ref); then I put it back. Direct shell
commands (`uv run ergostat check`) were refused in this session, so the check ran only through pytest. The factory's
own log of that run (`*-branch-check.txt`) is what would say why it printed nothing readable: a container or slot
failure, perhaps. This clone does not have it. I changed nothing in the model, because no change follows from what
I could see.

### Round 2, sent back: `competing-commands block.improve-factory`

The finding was right. `code-health-off` and `factory-off` were both controllers with `out: block.improve-factory`,
so the coordinator had two commanders. Now `code-health-off` outputs to `block.factory-off`, which reads it as a tenth
input (`code`) in its `max`. The coordinator is still asked when any code goal is off, but through one commander. That
touches `dev/model/measures.yaml` (2 lines and its description), which point 2 of round 2 had kept untouched. It is the
reversible option: point `code-health-off`'s `out` back and remove the `code` input to undo it.
`test_drift_turns_simplify_when_on` now asserts the new wire, that `improve-factory` has exactly one commander, and
that the root model has no `competing-commands` finding. Not run: Bash (and so pytest, ruff, `ergostat check` and
`git commit`) was refused in this session.

### Round 3: the round-2 fixes run

Bash ran this round, so the checks round 2 could not run were run here, at 8c7be35d (main b4639301 merged in; this
clone has no newer main):

- `tests/test_code_health_measures.py`: 5 passed, `test_check_on_the_root_model_reports_no_errors` included.
- `tests/test_code_health_simplifier.py` and `tests/test_factory.py`: 146 passed, 2 skipped. Both skips are in
  `tests/test_factory.py` (lines 1222 and 1477). They need Docker and the agent image, which this container does not
  have, and this branch does not touch them.
- `uv run ruff check ergostat tests scripts`: clean, and so is `dev/bin/measure.py`. With all of `dev/bin` added, ruff
  reports B023 at `dev/bin/plan.py:315` and E501 at `dev/bin/review.py:42`. This branch changes neither file, so both
  come from main and are left alone (lesson-13).
- Lesson-9 for round 2's single-commander fix: I pointed `code-health-off`'s `out` back at `block.improve-factory`,
  and `test_drift_turns_simplify_when_on` failed (`{'improve-factory'} == {'factory-off'}`). I put it back and the
  tests passed again.

Not run: `uv run ergostat check` as a command (refused again; the pytest check above runs it the way `[suites] check`
does), and the full unit suite and the four browser files (left to the factory's watchdogged run).
