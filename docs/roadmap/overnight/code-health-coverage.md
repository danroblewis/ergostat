# code-health-coverage: a coverage measure per module, and the modules below a floor named

depends-on: []

Sub-gap 1 of 5 of `code-health` (its definition: `docs/roadmap/overnight/code-health.md`). This comes first so that a
simplification never removes behaviour that no test covers. Branch `code-health-coverage`, from main.

**No new dependency.** pytest-cov and coverage are not in the dev group (`pyproject.toml`), and a session has no
network to update `uv.lock`. Python 3.12's standard `sys.monitoring` (LINE events, `DISABLE` after a line's first hit,
so each line costs one call) does the job without a package. If the owner later adds pytest-cov to the dev group, it
can replace the tracer behind the same report format.

## Definition of done

1. **The tracer.** `tests/coverage_lines.py` is a pytest plugin. It stays off unless `ERGOSTAT_COVERAGE=<dir>` is set,
   and then it records the executed lines of `ergostat/`, `dev/bin/` and `scripts/` in this process. Each xdist
   worker writes `<dir>/lines-<worker>.json`. Statement lines come from the files' `ast` (the lines a statement starts
   on, without docstrings), so the denominator does not depend on what ran.
2. **The report.** `scripts/coverage_report.py <dir>` combines the worker files into `<dir>/coverage.json`
   (`{module: {"statements", "covered", "share"}}`, plus the main sha and a `seq` taken from main's commit count). With
   `--below 0.6` it prints the modules under the floor, worst first. The floor is a number in `dev/factory.toml`
   (`[code_health] coverage_floor = 0.6`).
3. **The suite.** The queue's unit run on main sets `ERGOSTAT_COVERAGE` (in `dev/factory.toml`'s `[suites]`, so that
   only main's runs pay for it) and keeps the last report under `run/coverage/`. The fast unit suite's time is
   measured with and without the tracer, and both numbers go in "Where it stopped". If the overhead is more than 15%,
   the tracer runs on a nightly unit run instead, and the definition says so.
4. **The sensor.** `dev/bin/measure.py coverage-below-floor` gives the count of modules under the floor.
   `measure.py coverage NAME` gives one module's share. In `dev/model/measures.yaml` they are an auxiliary and a
   sensor. With no report, an unreadable report or a report older than main's last 20 merges, the measure has no
   value (exit 1, as `first-pass-yield` does), never 0 or 100%.
5. **What it does not see.** Code run only in a child process (the daemons, `python -m ergostat` under a subprocess,
   `dev/bin` programs called by path) is not traced. The report marks a module whose tests only reach it through a
   subprocess as `"subprocess-only": true` when the plugin saw it imported by no test, and the docs say that its
   share is a lower bound. Nothing calls it "untested".
6. `dev/README.md` (the factory's human doc) gets a short section on the measure, the floor and the list.

## Files to touch

`tests/coverage_lines.py` (new), `tests/conftest.py` (register the plugin when the variable is set),
`scripts/coverage_report.py` (new), `dev/bin/measure.py`, `dev/model/measures.yaml`, `dev/factory.toml`,
`dev/README.md`, `tests/test_code_health_coverage.py` (new).

## Risks

- lesson-3: a missing worker file, a missing report or a stale report read as 0% (everything "below floor") or as
  full coverage (nothing below). Each one must give "no value".
- lesson-8: "coverage per module" claimed for code that runs only in subprocesses. The claim is narrowed in the report
  and in the docs (point 5).
- lesson-10: the tracer's overhead pushing time-bound tests over their bounds under `-n 8`. The tracer is off by
  default, and the overhead is measured on the full suite, not on one file.
- lesson-2: "the latest report" picked by file mtime. Order by the `seq` stamped in it instead.
- lesson-9: a test that sets up a fully covered fixture module and checks only that a report exists.

## Acceptance tests

`tests/test_code_health_coverage.py`:
- `test_tracer_counts_executed_statement_lines`: a fixture module with one branch taken and one not reports exactly
  the taken lines covered, and its docstring is not counted as a statement.
- `test_workers_combine_into_one_report`: two worker files covering different lines of one module combine into their
  union.
- `test_below_floor_lists_worst_first`: three modules at 0.2, 0.5 and 0.9 with a floor of 0.6 give the first two, in
  that order.
- `test_missing_or_stale_report_has_no_value`: no report, a corrupt report and one 21 merges old all exit 1 from
  `measure.py coverage-below-floor`, and none prints 0 (lesson-3).
- `test_latest_report_by_seq_not_mtime`: an older report touched last is not the one read (lesson-2).
- `test_tracer_off_without_the_variable`: with `ERGOSTAT_COVERAGE` unset, `sys.monitoring` has no tool registered by
  the plugin.
- The unit suite and the four browser files under `scripts/suite_watch.py`, rc 0, ruff clean.

For each test, break the code it guards once and record in the report that it failed.

## Size budget

200 net lines of code outside `tests/`, `docs/` and `dev/` (`scripts/coverage_report.py`). The tracer is in `tests/`.
