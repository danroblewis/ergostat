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

### Round 2, by the implementor (answering review/code-health-coverage-1)

**Point 3 is still not done, and this session cannot do it.** Each command that set `ERGOSTAT_COVERAGE` (a one-file
probe with the variable before `uv run`, and again through `env`) was denied by the session's permission mode, as in
round 1. Running the tracer some other way, for instance from inside a test, would get around that denial instead of
respecting it, so it was not tried. Neither timing exists, `queue_coverage` stays `false`, and no real report of this
repository exists. As the review says, **the owner must take this measurement.** The two commands are now in
`dev/README.md` (*Coverage*). Round 1's "Left" put the variable before `scripts/in_container.sh`, but that script does
not pass the caller's environment into the container. The variable goes inside it:
`scripts/in_container.sh env ERGOSTAT_COVERAGE=run/coverage/probe uv run python scripts/suite_watch.py -- ...`. Then
either set `queue_coverage = true` (overhead 15% or less) or build the nightly run (more than 15%). The nightly run is
not built because the measurement that would call for it does not exist. Building it blind would be building what was
not asked. This is the second round, so by the house rules the branch should be parked or held for the owner, not
merged as done.

**The review's other findings (lesson-12), all answered in `dev/bin/queue.py`:**
- *The report's timeout escaped `suites()`.* `coverage_made` catches `TimeoutExpired` (and an `OSError`) and returns
  `"no report: timed out"`, so the queue run goes on.
- *A branch could score its own coverage.* The queue now runs `scripts/coverage_report.py` as it is in `pre` (main
  before the merge, by `git show`), with `--root` set to the merged checkout. If that script is missing, the result is
  "no report".
- *An unreadable report blocked the measure for up to five merges.* An unreadable `coverage.json` in a folder the queue
  made (matched by name) is now removed at once. Only the readable reports count toward the five kept.

**Tests.** New: `test_the_queue_scores_with_mains_script_and_survives_a_timeout`.
`test_the_queue_keeps_the_last_reports_by_seq` now also has an unreadable report next to the others. Each break below
was made alone and then undone:
- the script read from `HEAD` instead of `pre`: the new test failed (`'no report: the branch scores itself' != 'reported'`);
- `TimeoutExpired` not caught: the new test failed (the child raised);
- unreadable reports kept: `test_the_queue_keeps_the_last_reports_by_seq` failed (`gap-torn-…` left).

Run here: `tests/test_code_health_coverage.py` (9 passed), with `tests/test_factory.py` (50 passed, 2 skipped, its
Docker tests); `uv run ruff check ergostat tests scripts`, clean. Local `main` is this branch's merge base, so there was
nothing to merge in. There is no network to fetch origin. The unit suite and the four browser files were not run by
this session, which may not start the whole suite. The factory runs them after it.

### Round 2, suite fix round (the factory's unit run after round 2)

The unit run failed with one `F`, at about 82% of the dots, but its log names no test. It has no `FAILED` line or
short summary, and the run's tail stops before pytest's summary. Under `-n 8 --dist worksteal` a dot's position says
only when a test finished, not which test it was. So the test that failed is unknown, and **no code was changed**:
changing code without a named failure would be guessing (lesson-13). Checked again here, one file at a time, serially:
`tests/test_code_health_coverage.py` (9 passed), `tests/test_factory.py` (41 passed, 2 skipped),
`tests/test_ticket_factory_daemons.py` with `tests/test_model.py` (28 passed), and `tests/test_architecture.py`,
`tests/test_daemon_docs.py`, `tests/test_index_files.py`, `tests/test_factory_resources.py` and
`tests/test_factory_sessions.py` (59 passed). Those are the files that read what this branch changes: conftest,
queue.py, measure.py, factory.toml, measures.yaml, dev/README.md and scripts/. A serial run of the whole unit suite,
started to name the failure, was denied by the session's permission mode. With `ERGOSTAT_COVERAGE` unset (as in the
factory's run), the branch adds one `os.environ.get` per pytest process. Its own tests leave no global state behind:
the tracer test frees the `sys.monitoring` tool id it took, and its children write only under `tmp_path`. If the next
unit run names a test, that test is the next thing to look at. If it is a time-bound test, it belongs to lesson-10's
triage, not to this branch. Point 3 is still the owner's to measure, as round 2 says.

## Where it stopped

Parked by the factory (review/code-health-coverage-2, 2026-11-20 19:33).

Done: points 1, 2, 4, 5 and 6. These are the sys.monitoring tracer in tests/coverage_lines.py (off unless ERGOSTAT_COVERAGE is set), scripts/coverage_report.py (158 lines, inside the 200 budget), and measure.py coverage / coverage-below-floor, which fail closed when the report is missing, unreadable, stale or not on main and pick the latest report by seq. Also done: queue.py's opt-in tracer run (main's copy of the script, timeout caught, reports pruned by seq and by name), the measures.yaml auxiliary, the README section, and acceptance tests with a break check recorded for each. Left (point 3): time the fast unit suite with and without the tracer, using the two commands in dev/README.md (Coverage), and record both numbers in the definition. Then either set [suites] queue_coverage = true (overhead 15% or less) or build the nightly unit run (more than 15%), and confirm a first real report on main. Why stop: after three rounds the implementor's session still cannot set ERGOSTAT_COVERAGE, so the remaining step is the owner's measurement. Nothing partial should reach main.

**Measured by the coordinator (2026-11-20 23:50), in the container, through the suite slot, the machine otherwise
busy (9 implementors):** the fast unit suite without the tracer 273.0 s, with `ERGOSTAT_COVERAGE=run/coverage/probe`
255.1 s (both rc 0) — no measurable overhead (the difference is the machine's noise). The report was written: 8 worker
files combined into `coverage.json`, 346 modules. So `[suites] queue_coverage = true`.

### Continued, round 1, by the implementor (gap/code-health-coverage-continued)

**Point 3 is done.** The two numbers are the coordinator's, above: 273.0 s without the tracer and 255.1 s with it. That
is within the machine's noise and well under 15%, so `dev/factory.toml` now ships `[suites] queue_coverage = true` and
no nightly run is needed. `dev/README.md` (*Coverage*) says the tracer is on and gives the two times. The two commands
stay there for measuring again after a change to the tracer.

**Main merged in (0ecf249c).** The conflict was in `dev/bin/queue.py`. Main rewrote `suites()` to run unit and browser
together, keyed by a run tag, and replaced the single merge in `take()` with `land()`, which batches and bisects. The
merge keeps main's code. The branch's coverage step moves into `suites().one()`: only the `unit` suite gets the
`ERGOSTAT_COVERAGE=run/coverage/<tag>` prefix, and its report is scored by `coverage_kept` with the `pre` that `land()`
now passes in, which is main before the batch. So no merge in the batch scores its own coverage. A bisecting run's
tag ends in `-N`. `COVERAGE_RUN` now accepts that ending, so those folders are pruned by name like the rest.

**Decision taken alone (reversible):** during a bisect, every run, green or red, is traced. A red run's folder is
removed (as before), and a green prefix's report is kept and ordered by its seq. That seq counts the commits of the
prefix's head, which is not on main if that prefix never lands. `measure.py` already refuses a report whose commit is
not on main (`test_a_report_of_a_commit_not_on_main_is_not_read`), so such a report never gives a value.

**New test:** `test_the_queue_traces_only_its_unit_run` (on and off). It checks that only `unit` carries the prefix,
that the folder is `run/coverage/<tag>` with a `-N` tag, that the report is scored with the run's `pre`, and that with
the key off nothing is set. Each break below was made alone and then undone, and each failed the test:
- the regex without `(-\d+)?`;
- `"HEAD"` passed in place of `pre`;
- the prefix put on every suite, not only `unit`.

**Tests run here:** `tests/test_code_health_coverage.py` (11 passed) and `tests/test_factory.py` (57 passed,
2 skipped: its Docker tests), each alone; `uv run ruff check ergostat tests scripts`, clean. This session did not run
the unit suite or the four browser files (the factory runs them). The first report from the queue itself will exist
after the first green queue run once this lands.

### Continued, round 1, suite fix round (the factory's unit run after the continued round)

The merge of main (0ecf249c) was already committed (`d9527bfe`), so nothing was left to resolve. The unit run's tail
stops partway through a line of dots at 72%. It has no `F`, no `FAILED` line, no summary and no closing
`{"rc": ...}` from suite_watch, so no test failed in what it shows. The run was cut off before it finished, as in
round 1's suite fix round. **No code was changed**: with no test named, a change would be a guess (lesson-13). The
config flip (`queue_coverage = true`) does not reach the tests. `fac.config()` reads only `FACTORY_CONFIG` when it is
set, every test that runs the queue writes its own `factory.toml` without the key, and the factory's unit run has
`ERGOSTAT_COVERAGE` unset. Each subprocess this branch's tests start has a timeout (60 to 300 s), so none of them can
hang the run. A serial, verbose whole-suite run, started to name a hanging test, was denied by the session's
permission mode. Checked here instead, one invocation at a time: `tests/test_code_health_coverage.py` (11 passed),
`tests/test_factory.py` (57 passed, 2 skipped, its Docker tests), and `tests/test_factory_resources.py`,
`test_architecture.py`, `test_daemon_docs.py`, `test_index_files.py`, `test_factory_sessions.py`,
`test_ticket_factory_daemons.py` and `test_model.py` together (87 passed). `uv run ruff check ergostat tests scripts`
is clean. If the next unit run names a test, that test is the next thing to look at.

### Continued, round 2, by the implementor (the merge of main 24756e50)

The merge conflicted only in `dev/bin/measure.py`'s module docstring. Main added the `in-STATE-hours`, `loop-*` and
`gate-*` lines (times.py), and the branch added `coverage-below-floor` and `coverage NAME`. Both are kept: main's lines
come first, with "The last three..." after them, then the branch's two coverage lines and their no-value note. The code
merged cleanly: `reading()` dispatches to `times.reading` as on main, and `main` sends `coverage` and
`coverage-below-floor` to `coverage_reading`. Nothing else changed. Run here, one invocation at a time:
`tests/test_code_health_coverage.py` (11 passed), `tests/test_factory_times.py` (7 passed), `tests/test_factory.py`
(59 passed, 2 skipped: its Docker tests), and `tests/test_factory_knowledge.py`, `test_daemon_docs.py` and
`test_architecture.py` together (90 passed). `uv run ruff check ergostat tests scripts` is clean. This session did not
run the unit suite or the four browser files. The factory runs them after it.

### Continued, round 2, suite fix round (the factory's unit run after the merge of 24756e50)

The merge of main was already committed (`241430c8`, noted in `d0b649ed`), and `git status` was clean, so nothing was
left to resolve. The unit run's tail stops after 19 dots, just after xdist brought up its nodes. It has no `F`, no
`FAILED` line, no summary and no closing `{"rc": ...}` from suite_watch, so no test failed in what it shows. The run
was cut off from outside, as in the earlier suite fix rounds. **No code was changed**, because with no test named any
change would be a guess (lesson-13). Run again here, one invocation at a time: `tests/test_code_health_coverage.py`
(11 passed), `tests/test_factory.py` (59 passed, 2 skipped: its Docker tests), and `tests/test_factory_resources.py`,
`test_architecture.py`, `test_daemon_docs.py`, `test_index_files.py`, `test_factory_sessions.py`,
`test_ticket_factory_daemons.py`, `test_model.py` and `test_factory_times.py` together (94 passed).
`uv run ruff check ergostat tests scripts` is clean. If the next unit run names a test, that test is the next thing to
look at.

### Continued, round 3, by the implementor (the merge of main 278666f7)

The merge conflicted only in `dev/bin/measure.py`'s `__main__`. Main now passes a second argument to `reading()` as
`kind=` (the `parks`, `resumes` and `parked-hours KIND` measures, parks.py). The branch sends `coverage` and
`coverage-below-floor` to `coverage_reading` with the rest of the arguments. Both are kept: the two coverage names go
to `coverage_reading`, and every other name goes to `reading(name, kind=...)` as on main. The docstring had merged
cleanly and holds both sides. Nothing else changed. Run here, one invocation at a time:
`tests/test_code_health_coverage.py` (11 passed), `tests/test_factory.py` (66 passed, 2 skipped: its Docker tests), and
`tests/test_factory_knowledge.py`, `test_factory_times.py`, `test_daemon_docs.py` and `test_architecture.py` together
(97 passed). `uv run ruff check ergostat tests scripts dev/bin` is clean. This session did not run the unit suite or
the four browser files. The factory runs them after it.
