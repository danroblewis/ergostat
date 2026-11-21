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

## Where it stopped

Round 1, by the implementor. Points 1, 2, 4, 5 and 6 are built. **Point 3 is not done: the overhead was not
measured**, so the queue's tracer ships off (see below).

**Built.**
- `tests/coverage_lines.py`: the tracer (`sys.monitoring` LINE events with `DISABLE`, on its own tool id), registered
  from `tests/conftest.py`'s `pytest_configure` only when `ERGOSTAT_COVERAGE` is set. Each xdist worker (or the one
  process of a serial run, as `main`) writes `lines-<worker>.json` with its lines, the traced files it imported, the
  worker count and xdist's run id. xdist's controller runs no test and writes nothing.
- `scripts/coverage_report.py` (158 lines, inside the 200): statements from `ast` (a statement's start line; a line run
  anywhere in its own lines, such as a continuation or a decorator, covers it; docstrings, `global` and `nonlocal` are
  not counted). The worker files are combined into `coverage.json` (`{"main", "seq", "modules": {...}}`), and
  `--below` lists the modules under the floor, worst first. If a worker's file is missing, unreadable or from another
  run, the script writes no report and exits 1. `"subprocess-only": true` marks a module that no worker imported.
- `dev/bin/measure.py coverage-below-floor` and `coverage NAME`, with the auxiliary and sensor in
  `dev/model/measures.yaml`. There is no value (exit 1, nothing on stdout) when there is no report, when any report is
  unreadable (it may be the latest), when no report is of a commit on main (one whose merge the queue undid), or when
  the latest is more than 20 of main's first-parent commits old. A missing or invalid `[code_health] coverage_floor`
  also gives no value.
- `dev/bin/queue.py`: with `[suites] queue_coverage = true`, the queue's unit run is prefixed with
  `ERGOSTAT_COVERAGE=run/coverage/<run tag>`. The report is made after a green unit run. Reports are kept by seq, the
  last five; a red run's folder, or one that made no report, is removed by name.
- `dev/README.md`, *Coverage: the modules below a floor*.

**Decisions taken alone (each reversible).**
- `seq` is `git rev-list --count --first-parent HEAD`, main's merges and direct commits, and staleness is
  `rev-list --count --first-parent <sha>..main > 20`. Plain commit counts would count every commit of a branch
  merged.
- The definition's "in [suites], so that only main's runs pay" was found wrong by review/code-health-1: `[suites]`
  runs in the implementor's worktree too. So the variable is not in a suite command. `[suites] queue_coverage` is a
  key only `queue.py` reads, and it prefixes the queue's own unit command.
- **`queue_coverage` ships `false`.** This session could not run any command that sets `ERGOSTAT_COVERAGE` (the
  session's permission mode denied each attempt), and its brief forbids running the whole suite in parallel. So
  neither number of point 3 exists. Turning on a tracer of unmeasured overhead in main's queue risks lesson-10, with
  time-bound tests failing under `-n 8` on every merge. Off is one key to flip. Until it is flipped,
  `coverage-below-floor` has no value (exit 1), which is its designed behaviour.

**Left.**
- Measure the fast unit suite with and without the tracer: `scripts/in_container.sh uv run python
  scripts/suite_watch.py -- uv run python -m pytest -q -n 8 --dist worksteal`, and the same with
  `ERGOSTAT_COVERAGE=run/coverage/probe` before `uv run`. Record both numbers here. If the overhead is 15% or less, set
  `queue_coverage = true`. If it is more, the tracer belongs on a nightly unit run instead (not built here).
- The first real report on this repository has not been made, for the same reason. Its numbers (how many modules are
  below 0.6, how many are subprocess-only) are not known.

**Tests run** (one file at a time, not the whole suite): `tests/test_code_health_coverage.py`, 8 passed;
`tests/test_factory.py`, 41 passed, 2 skipped (its Docker tests); `uv run ruff check ergostat tests scripts`, clean.
The unit suite and the four browser files were not run by this session; the factory runs them after it.

**Each test broken once (lesson-9).** Each change below was made and then undone. Each was alone,
except the staleness and the by-seq changes, made together because each touches only its own test's case:
- docstrings counted as statements: `test_tracer_counts_executed_statement_lines` failed (and the combine test, whose
  count changed);
- the last worker's lines kept instead of the union: `test_workers_combine_into_one_report` failed;
- the modules below the floor sorted by name: `test_below_floor_lists_worst_first` failed;
- staleness at `> 21`: `test_missing_or_stale_report_has_no_value` failed;
- the report read last by path instead of by seq: `test_latest_report_by_seq_not_mtime` failed;
- an unreadable report skipped instead of having no value: no test failed at first, because a corrupt report alone
  gives no value either way. The test now also puts a readable report next to the corrupt one, and with the break it
  failed;
- the plugin registered without the variable (in both `conftest.py` and `register()`): `test_tracer_off_without_the_variable`
  failed;
- the queue's reports pruned by folder name instead of by seq: `test_the_queue_keeps_the_last_reports_by_seq` (an
  addition) failed.

**The factory's unit run after round 1 (suite fix round).** It was reported failed, but its log stops after uv's
install lines. pytest's dots, xdist's "bringing up nodes" and suite_watch's closing `{"rc": ...}` line are all missing.
`fac.suite` sets no timeout, so the run was stopped from outside before it finished. Output written to a file is
block-buffered, so a killed run leaves nothing. No failing test is named, so nothing in the code was changed. Checked
again in this round, one file at a time (the session may not start the whole suite):
`tests/test_code_health_coverage.py` (8 passed, serial, and again with `-n 4 --dist worksteal` in random order next to
`tests/test_factory_resources.py`, 16 passed), `tests/test_factory.py`, `tests/test_factory_resources.py` and
`tests/test_ticket_factory_daemons.py` (55 passed, 2 skipped), and the full suite's collection (2002 tests, no error).
Ruff is clean. With `ERGOSTAT_COVERAGE` unset, the branch adds one `os.environ.get` per pytest process to the unit run.
If the unit suite fails again with a named test, that test is the next thing to look at.

Also added: `test_a_report_of_a_commit_not_on_main_is_not_read`. `test_tracer_off_without_the_variable` also runs the
tracer for real in a child pytest with the variable set, and checks that a module the probe imported
(`ergostat/durations.py`) is in its file.
