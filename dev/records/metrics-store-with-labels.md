# metrics-store-with-labels: ergostat's own series are queryable by PromQL with real labels

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Problem. ergostat's series are flat names in SQLite (414 here), with no labels. ergostat/victoria.py already supports VictoriaMetrics, writing `ergostat_reading{project,series}`.

Change.
- VictoriaMetrics becomes the recommended metrics store for dashboards: how to obtain and run it, declared as a process ergostat supervises, and an idempotent migration of existing readings.
- Series can carry bounded labels, and readings appear under names and labels a person can query.
- ergostat's own store appears as a built-in Prometheus-compatible data source.
- With SQLite, PromQL panels say what is needed and the rest of the page works.

Definition of done.
1. A test against a real VictoriaMetrics binary (skipped when absent) migrates a record, with every reading preserved, and answers PromQL.
2. Running the migration twice changes nothing.
3. The guide says how to turn it on. Do not change any live instance: the coordinator does that.

## Owner's decision, 2026-11-23

VictoriaMetrics is the default metrics store for new installs, so a fresh install's dashboard has data. An existing SQLite install keeps working until it migrates. Test how VictoriaMetrics computes `rate()` and `increase()` against Prometheus and record the differences.

## Where it stopped

Round 1 stopped before any building, 2026-11-23. The session's tool permissions refused every shell command: both
`git -C /work status --short` and a first read-only look (`cat ... && which victoria-metrics ...`) were denied
("don't ask mode"). With no shell, the session could not run pytest, ruff or a VictoriaMetrics binary, and could not
`git add` or `git commit`. That means none of done items 1-3 could be tested, and the branch could not record any
work. This section is written to the working tree but is **not committed**, because committing needs the shell too.

Done: nothing outside this section. ergostat/victoria.py, CLAUDE.md and this definition were read.

Left: all of it. That covers the migration with its idempotence test against a real binary (skipped when absent),
bounded series labels, the built-in Prometheus-compatible data source, the SQLite message on PromQL panels, the
supervised VictoriaMetrics process, the guide text, and the `rate()`/`increase()` comparison against Prometheus.

Why: this is the environment, not the gap. No dependency is missing. I chose the most reversible option and wrote
no untested code into the tree. Rerun the round with Bash allowed (at least `git`, `uv run`, and the test and ruff
scripts).

## Where it stopped

Parked by the factory (review/metrics-store-with-labels-1, 2026-11-23 09:15).

Done: only the definition of done and a Where it stopped note, committed. Left: everything in the definition (migration plus idempotence test against a real VictoriaMetrics binary, bounded labels, the built-in Prometheus data source, the SQLite PromQL-panel message, the supervised process and default-for-new-installs, the guide text, the rate()/increase() comparison). Why stop: the build session's tool permissions refused every shell command, so it could not run git, uv, pytest, ruff or the binary. A fix round in the same environment would fail the same way. This is an environment cause, not a fault in the gap's approach.

## Where it stopped

Round 2 stopped before any building, 2026-11-23. The queue's note said the shell fault was gone, but it was not:
the session's tool permissions again refused every shell command ("don't ask mode"). Two commands were refused, as
given: `git status --short && git log --oneline -3 && wc -l CLAUDE.md NOTES.md ergostat/victoria.py && cat
ergostat/victoria.py && which victoria-metrics victoria-metrics-prod ...`, and then the plain
`git -C /work status --short`. Without a shell this session cannot run pytest, ruff, `scripts/named_tests.py` or a
VictoriaMetrics binary, and cannot `git add` or `git commit` (a third command, `git -C /work add
dev/records/metrics-store-with-labels.md && git -C /work commit -m "..."`, was refused too). This section is written to the working tree only and is
**not committed**.

Done: nothing outside this section.

Left: everything in the definition, as listed in the round-1 note above.

Why: the environment, for the second time in a row. No dependency is missing. I took the most reversible option and
wrote no untested code: code that cannot be run or committed would fail review (done means tests pass and the work is
committed). Do not schedule round 3 until a session's Bash is shown to work, for example by running
`git -C /work status --short` as the session's first command before the gap is handed over.

## Where it stopped

Parked by the factory (review/metrics-store-with-labels-2, 2026-11-23 14:49).

Done: only the definition of done and the stopped-round notes are committed (0 core lines). Left: everything in the definition. That is the idempotent SQLite-to-VictoriaMetrics migration with a test against a real binary (skipped when absent) that keeps every reading and answers PromQL, a test that running it twice changes nothing, bounded series labels, the built-in Prometheus-compatible data source, the SQLite message on PromQL panels, VictoriaMetrics as a supervised process and the default for new installs, the guide text on turning it on, and the rate()/increase() comparison against Prometheus. Why stop: in three rounds, every build session's shell commands were refused ('don't ask mode'), so no code could be run, tested or committed. Another round in the same environment would fail the same way. The cause is the environment, not the gap's approach.

## Where it stopped

Round 3: built, 2026-11-23. The shell worked once each call was one plain command, as the queue's note said. About 210
net lines outside tests, docs and dev (budget 600).

Answering the queue's findings: the shell was not broken, and every call here was one allowed command. One was refused,
as given: `uv run python scripts/suite_watch.py -- uv run python scripts/named_tests.py tests/test_daemons.py
tests/test_daemon_yaml_review.py tests/test_spec_structure.py`. The same three files then ran without the watchdog. The
build order asked for was kept: (1) the built-in source, (2) the migration and its tests, (3) the labels, (4) the rest.
(1) and (3) went into one commit, because the source's names are the labels.

Done, by the definition:
- **Bounded labels** (`victoria.promql_name`). Each series is written under a name and labels taken from its own
  structure. For example, `sensor/queue.depth` becomes `ergostat_sensor{part="queue",sensor="depth"}`, and
  `run/BLOCK/cost_usd` becomes `ergostat_run_cost_usd{block="BLOCK"}`. Valves, blocks, observers and the rest are in
  the SPEC §4b table. Every series also carries `project` and `series`. Every label's value is a name the model
  declares, so nothing generated is ever a label.
- **The built-in source** (`datasources.sources`). `ergostat` is a `prometheus` source over the project's
  VictoriaMetrics. It is held to the project by VictoriaMetrics' `extra_label=project=...`, which the server applies
  whatever the text says. A model's own source named `ergostat` wins. `query`, `suggest` and `query/fields` are given
  the project's store.
- **The SQLite message.** Over SQLite the built-in source is not listed. A panel naming it is refused in its own result
  (`refused`), naming VictoriaMetrics, `storage: measurements: victoriametrics` and `ergostat migrate`. The page's
  other panels are answered.
- **The migration.** `ergostat migrate [--url] [--dry-run]` (`ergostat/migrate.py`) copies every reading SQLite answers
  (raw, and each old bucket's last reading). It also renames a VictoriaMetrics record under the old single name
  `ergostat_reading`. For each series it sends only what the server does not hold under the new name (same
  millisecond, same value), so a second run sends nothing.
- **Supervised.** `storage: measurements: run:` becomes the daemon `victoriametrics`. It is started though nothing
  uses it, and restarted, given up and stopped as every daemon is. A `daemons:` entry of that name is an error.
- **The default for new installs** (`storage.measurements_backend`). If the YAML names no backend:
  - A record with a `measurements.db` keeps SQLite.
  - A new record takes VictoriaMetrics when one answers `/health` at 127.0.0.1:8428, and leaves a mark, so a server
    that is away later is never read as "use SQLite". Otherwise it uses SQLite.
  - `ERGOSTAT_DEFAULT_MEASUREMENTS` overrides this. `tests/conftest.py` sets `sqlite`, so no test reaches a live
    server.
- **A record from before the labels.** Every read takes `ergostat_.+`, so a series written partly under the old name
  is read whole until it is migrated (`_range` merges, and `series()` sums).
- **The guide**: docs/DASHBOARDS.md §6a, *turning on VictoriaMetrics*. It covers getting it, `run:`, migrate, the
  default and what to write. SPEC §4b and §4e say the same.
- **rate() and increase()**: recorded in SPEC §4e. Prometheus extrapolates toward the window's edges, needs two
  samples and can give a fractional increase. VictoriaMetrics counts from the sample before the window and does not
  extrapolate. The test case gives 1.125 against 1.

Choices taken without asking (the most reversible):
- **The default.** It switches only when a server already answers, because ergostat starts nothing of its own accord
  (invariant 12). A fresh install with no VictoriaMetrics stays on SQLite. Undo: delete `measurements.backend`, or
  name the backend.
- **A known cost.** SPEC §4b had kept SQLite as the default because the engine's reads through VictoriaMetrics were
  slow (under one reading a second, against six). The owner's decision overrides that. The measurement was not
  repeated here, and SPEC says so.
- **Labels.** They are derived from the series' names, not declared per sensor. Declared labels would need a labelled
  `add` through every writer. They are not built.
- **Not copied.** The backfill ledger is not copied by `migrate`, and SPEC says so.
- **Start-up.** While the supervised server starts (about a second), the engine's writes fail, as whenever the server
  is away. That behaviour was already there, and changing it is outside this gap.

Acceptance tests (`tests/test_metrics_store_labels.py`, 15):
- Done 1: `test_a_record_is_migrated_with_every_reading_and_answers_promql`, against a real binary. It checks the
  readings are identical, PromQL by label, and another project's series not seen.
- Done 2: `test_migrating_twice_changes_nothing`, against a real binary.
- Also against a real binary: `test_a_record_under_the_old_single_name_is_renamed_once` and
  `test_rate_and_increase_differ_from_prometheus_as_recorded`.
- These four need a server. They start one from `ERGOSTAT_TEST_VM_BIN` or `victoria-metrics` on the PATH, or use
  `ERGOSTAT_TEST_VM_URL`. Otherwise they skip with the queue's exempt reason. **No binary is in this container, so
  all four were skipped here and have never run.** Their VictoriaMetrics expectations come from its documentation.
- Run here: `test_the_migration_sends_each_reading_once_and_renames_the_old_name`. It runs the same migration code
  over an in-memory stand-in for the server: every reading once, twice changes nothing, then a later reading sent
  alone.
- Also run here: the source, SQLite-message, default, supervised, CLI, naming and mixed-name tests.
- Done 3 is the guide. No live instance was changed.

Seen to fail when the code they guard was broken, all four at once, then put back:
- removing `_needs` failed the SQLite test;
- dropping `extra_label` failed the built-in source test;
- dropping the store daemon from `used` failed the supervised test;
- ignoring what the server holds failed the in-memory migration test (757 sent, not 756).

Run here, one file at a time:
- test_metrics_store_labels: 11 passed and 4 skipped as above (15 tests). Before the CLI test was added, it ran
  with test_upkeep_record: 24 passed.
- test_data_sources, test_storage and test_spec_schema: 64 passed.
- test_store_conformance, test_upkeep_record and test_cli_fallback: 78 passed, 12 skipped (VictoriaMetrics).
- test_dashboards_doc and test_daemon_docs passed.
- test_daemons, test_daemon_yaml_review and test_spec_structure: 78 passed.
- test_web_lanes, test_web_access and test_daemons_restart: 43 passed.
- test_data_source_panels (browser, under the watchdog): 3 passed, rc 0, none skipped.
- ruff is clean.
- test_query_engine: 114 passed, 1 failed in the batch.
  `test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log` took 0.111 s on the `counts` source,
  which this branch does not touch. It passed when run alone. It is a timing bound under load, not this change.

Not run here: the whole unit suite, the four browser files and `demo_check` (no example touched). `main` (278f54a4)
was already merged and has not moved.

## Entry

section: Runtime, scale and latency

- **ergostat's own series in PromQL, with real labels** (done, on `metrics-store-with-labels`; SPEC §4b, §4e;
  docs/DASHBOARDS.md §6a). On VictoriaMetrics, each series is named with bounded labels (`ergostat_sensor{part,
  sensor}`, `ergostat_run_cost_usd{block}`, ...). The built-in `ergostat` data source answers PromQL for the project's
  own series; over SQLite, a panel naming it says what it needs. `ergostat migrate` copies the readings idempotently,
  reads each series back, and fails naming any reading the server did not keep (its `-retentionPeriod`).
  `storage: measurements: run:` supervises the server, and a new record under the default home (`~/.ergostat`)
  takes VictoriaMetrics when one answers; any other `ERGOSTAT_HOME` stays on SQLite unless asked. Left:
  the five real-binary tests have not been seen to pass (no binary where it was built); labels declared per sensor;
  the engine's reads through VictoriaMetrics were measured slow before and are not re-measured.

## Where it stopped

Round 4, the fix round: built, 2026-11-24. About 240 net lines outside tests, docs and dev in all (budget 600).

The review's findings, both blocking, both answered (there were no others):
- **Readings counted as sent without being kept** (migrate.py `_send`). Each series is now read back after it is
  sent. A reading the server lacks after the send counts as `missing`, not as sent, and is named by series in `lost`
  (`{n, first, last}`). `ergostat migrate` then exits 1 and prints each such series with its count and the days it
  spans. It names `-retentionPeriod` and does not suggest switching the backend (the JSON form exits 1 too). A series
  under the old name `ergostat_reading` is deleted only when every one of its readings is held under the new name, so
  a lost reading is never deleted from the server. A rerun sends the lost readings again and says `missing` again,
  never "sent nothing". The guide (§6a) now warns that `-retentionPeriod` is one month unless set, against SQLite's
  up to 730 days, for `run:` and for a server run by hand. SPEC §4b, the CLI help and the docstrings now say "once
  every reading is held, a rerun sends nothing".
- **Values matched by `.12g` text** (`_key`). A reading is now held when a value at the same millisecond is within a
  relative 1e-9 (`migrate.TOL`, `math.isclose`; NaN matches NaN). The in-memory stand-in now keeps values as a lossy
  server would, cut (not rounded) to 12 significant digits. The record has a series of long floats (1/3, 2/3,
  0.1+0.2, 1e-7, 123456.789012345, pi*1e9, 2/3*1e-12, -1/7, 0), and the real-server tests compare values to 1e-10
  relative and run on the same record.

New tests: `test_readings_the_server_does_not_keep_are_named_not_counted_as_sent` (in-memory, retention one day), an
extension of `test_ergostat_migrate_says_what_it_sent_and_a_server_away_fails_it` (exit 1, the stderr names the
series, no "To read them from there"), and `test_readings_a_real_server_drops_are_named_not_counted_as_sent`, a real
binary started with `-retentionPeriod=1d` (needs `ERGOSTAT_TEST_VM_BIN` or PATH, skipped otherwise).

Seen to fail when the code they guard was broken, each put back after:
- going back to the `.12g` match failed the in-memory migration test: 17 readings were never counted as held,
  including `0.01*7` costs.
- skipping the read-back failed the retention test (missing 0, not 734) and the CLI test (exit 0, with "sent 1" and
  the switch-over hint).
- deleting the old name despite a loss failed the retention test (renamed 1, not 0).

Not proven: **no VictoriaMetrics binary is in this container**, so the five real-server tests were skipped again and
have never run. The tolerance assumes the server keeps at least 10 significant digits (its documentation says about
12). That is a reading of the documentation, not a measurement.

Run here, one file at a time: test_metrics_store_labels gave 12 passed and 5 skipped (the real-server tests). With
test_storage and test_daemon_docs it gave 48 passed and 5 skipped. test_dashboards_doc, test_cli_fallback and
test_spec_structure gave 63 passed. ruff is clean. `main` was already merged (it is an ancestor of HEAD). Not run: the
whole unit suite, the browser files (no page changed) and `demo_check` (no example touched).

## Where it stopped

Round 5, the fix round: built, 2026-11-24. No code outside tests changed this round (one test line).

The queue's one finding (blocking), answered:
- **The old-name test's expected dict had drifted.** `test_a_record_under_the_old_single_name_is_renamed_once`
  compared the second run with a dict that had no `missing` or `lost`, but `migrate` has returned both since round 4.
  So on any host with a binary, this test would have failed every time. It now expects
  `{"series": 0, "readings": 0, "sent": 0, "renamed": 0, "missing": 0, "lost": {}}`.
- **The other four real-server tests, re-read for the same drift.** No other drift was found:
  - `test_a_record_is_migrated_with_every_reading_and_answers_promql` already names all six keys.
  - `test_migrating_twice_changes_nothing` compares `{**first, "sent": 0}`, which carries `missing` and `lost` over
    from the first run.
  - The retention test reads only `sent`, `lost` and `missing`.
  - The rate/increase test does not call `migrate`.

Still not proven: **no VictoriaMetrics binary is in reach**. `which victoria-metrics victoria-metrics-prod vmsingle`
finds none, and fetching one would reach the network, which this session may not do. So the five real-server tests
skipped again, and done items 1 and 2 still have no passing run behind them. The fix above was checked only by reading
it against `migrate.py:63`, not by running it. The step left for the coordinator: run
`tests/test_metrics_store_labels.py` with `ERGOSTAT_TEST_VM_BIN` set to a VictoriaMetrics binary before landing.

Run here: test_metrics_store_labels gave 12 passed and 5 skipped (the real-server tests). ruff is clean. `main` is an
ancestor of HEAD. Not run: the whole unit suite, the browser files and `demo_check` (nothing they cover changed).

## Where it stopped

Round 6: the merge of main (b9341591), 2026-11-24. The one finding was the three conflicted files. All three
conflicts were the same thing: main added a `project=` argument (the project asking, for its new `sql` source, through
`ASKING`), and the branch added `store=` (the project's measurements, for the built-in `ergostat` source). Each was
resolved by keeping both:
- `datasources.query(..., store=None, project=None)` and `datasources.suggest(..., store=None, project=None)`;
- `query/engine.py` `_from_source` passes `store=p.measurements, project=p`;
- `web/server.py` `_suggest` passes `store=p.measurements, project=p`.
No other code changed this round.

Run here after the merge:
- test_metrics_store_labels, test_data_sources and test_sql_source: 39 passed, 5 skipped (the real-server tests).
- test_query_engine, test_storage and test_web_access: 85 passed.
- test_data_source_panels and test_sql_editor (browser, under the watchdog): 5 passed, rc 0, none skipped.
- ruff is clean.

Still not proven: no VictoriaMetrics binary is in this container (`which victoria-metrics victoria-metrics-prod
vmsingle` finds none), so the five real-server tests skipped again, and done items 1 and 2 have no passing run. The
coordinator should run `tests/test_metrics_store_labels.py` with `ERGOSTAT_TEST_VM_BIN` set before landing. Not run:
the whole unit suite, the four browser files and `demo_check` (no example touched).

## Where it stopped

Round 7, the fix round: built, 2026-11-24. About 20 net lines of code changed this round (storage.py and
cli/record.py), well inside the budget.

The queue's one finding (blocking), answered in each of its parts:
- **Throwaway homes wrote into a live server.** I took the finding's second option, which is the most reversible: the
  probe is taken only for the default home. `storage.in_default_home(d)` is true only when the record's directory sits
  directly under `~/.ergostat`. A new record under any other `ERGOSTAT_HOME` takes SQLite without asking the server,
  even when one answers at 127.0.0.1:8428. That covers every script the finding names (demo_check, demo_up, loadtest,
  latency_bench, scale_bench, factory_fixture), and also daemon_bench, gated_check, authoring_bench, layout_survey,
  modelling_well_shots, dev/conformance, library trial and author, with no edit to each. So their readings never reach
  the live server, never share its `project` label, and the benchmarks measure the SQLite store they report.
  `ERGOSTAT_DEFAULT_MEASUREMENTS=victoriametrics`, or the YAML naming the backend, still asks for it under any home.
  - The cost of this choice: an owner who runs a real install under a non-default `ERGOSTAT_HOME` does not get the
    automatic default. They name the backend in the YAML or set the variable. The guide (§6a) and SPEC §4b say so.
    To undo it, drop the `in_default_home(d) and` condition in `storage.measurements_backend`.
- **`ergostat reset --yes` switched a SQLite install.** When reset deletes a `measurements.db`, it now writes the mark
  `measurements.backend` = `sqlite`. The mark is not in the reset's delete list, and storage reads it before any probe,
  so the reset record stays SQLite. A record that was VictoriaMetrics-backed keeps its own mark, as before.
- **The test the finding asked for.** `test_a_fresh_ergostat_home_never_writes_to_a_server_answering_unless_asked`
  uses a stub server answering `/health` OK at VM_URL, a fresh `ERGOSTAT_HOME`, and no backend in the YAML. It writes a
  reading through a real `Project`. The record is SQLite, no mark is left, the stub received no request at all, and the
  same home with `ERGOSTAT_DEFAULT_MEASUREMENTS=victoriametrics` takes VictoriaMetrics. Also new:
  `test_reset_keeps_a_sqlite_record_on_sqlite`, which runs under the default home with a server answering. After
  `reset --yes` the record is still SQLite, while a new record beside it is still asked. The default test from round 3
  now places its records under a default home (`HOME` set to the test's folder).

Seen to fail when the code they guard was broken, then put back:
- probing for every home failed the throwaway-home test (the reading went to the stub's `/api/v1/import`);
- not writing the reset mark failed the reset test (`victoriametrics`, not `sqlite`).

Still not proven: no VictoriaMetrics binary is in this container (`which victoria-metrics victoria-metrics-prod
vmsingle` finds none), so the five real-server tests skipped again. Done items 1 and 2 still have no passing run behind
them. The coordinator should run `tests/test_metrics_store_labels.py` with `ERGOSTAT_TEST_VM_BIN` set before landing.

Run here, one file at a time:
- test_metrics_store_labels: 14 passed, 5 skipped (the real-server tests).
- test_dashboards_doc, test_storage and test_spec_structure: 52 passed.
- test_graph_cli_web::test_reset_forgets_the_record_and_nothing_else, test_cli_fallback and test_data_sources: 37
  passed.
- ruff is clean.

`main` (b9341591) is already merged and has not moved. Not run: the whole unit suite, the four browser files (no page
changed) and `demo_check` (no example touched).

## Where it stopped

Round 8, a merge of main and a fix round: built, 2026-11-24. About 20 net lines of code this round, inside the budget.

**The merge of main (e8669794).** Three files conflicted. In each one, main had added the built-in `model` source
(`_sources`, `own`, `listed(own_only=)`) and `public=` for public readers, while the branch had added `store=` and the
built-in `ergostat`. I kept both:
- `datasources.sources(spec, store)` now gives the declared sources, plus `model` (main's rule: when there is a spec
  and no declared source is named `model`), plus `ergostat` (when a store is given).
- `listed(spec, store=None, own_only=False)` and `query(..., store=None, project=None, public=False)` take both
  sets of arguments.
- `own()` stays as it is on main: only the `model` type counts as the project's own. So the built-in `ergostat`, which
  reads a server, is never answered for a public reader. That is the fail-closed choice.
- `engine._from_source` passes `store`, `project` and `public`, and `fields._read` keeps main's `pipelines`.
- Two branch tests had expected the listing to be exactly `[]` or exactly `[ergostat]`. Since main, that listing also
  holds `model`, so the tests now check membership. One of them also asserts that `own(spec, "ergostat")` is false.

**The finding (blocking): `ergostat reset` on a VictoriaMetrics record.** I took the finding's first option.
- With `--yes`, `cmd_reset` calls `measurements.drop()` before deleting anything local. `drop()` sends
  `delete_series` for `{__name__=~"ergostat_.+",project=...}`. That covers every name, including the old
  `ergostat_reading`, and it also covers the readings that `forget` set aside, which are in the server.
- If the server is away, the reset is refused (exit 1). Its stderr names VictoriaMetrics, and nothing local is deleted
  (lesson 3).
- `RECORD` now includes `measurements.backfilled.db` and its `-shm` and `-wal` files, so a later `--backfill` of the
  same file is sent again.
- Without `--yes`, the command also says that it would delete every reading of the project in VictoriaMetrics at the
  server's address.
- The `measurements.backend` mark stays `victoriametrics`, which is now consistent because the server holds nothing
  for the project.
- The help text, the docstring, SPEC §4b (*The default*) and docs/DASHBOARDS.md §6a now say all of this.

The new test, `test_reset_of_a_victoriametrics_record_deletes_its_series_in_the_server`, runs against the stub server,
which now records POSTs. It checks four things:
- plain `reset` sends nothing and names the server;
- `reset --yes` sends exactly one `delete_series` with the project's selector;
- the backfill ledger and `forgotten.json` are gone;
- a server that is away gives exit 1 and leaves the local files.

I broke the code to check the test can fail: with the `drop()` call skipped, the test failed (the stub received
nothing). The call is back in place.

Still not proven: no VictoriaMetrics binary is in this container, so the five real-server tests were skipped again.
Done items 1 and 2 still have no passing run behind them. The coordinator should run
`tests/test_metrics_store_labels.py` with `ERGOSTAT_TEST_VM_BIN` set before landing.

Run here, one file at a time (three at most per call):
- test_metrics_store_labels, test_data_sources and test_model_data_source: 69 passed, 5 skipped (the real-server
  tests).
- test_sql_source, test_query_engine and test_graph_cli_web: 120 passed.
- test_dashboards_doc, test_cli_fallback and test_storage: 59 passed.
- test_data_source_panels (browser) and test_spec_structure, under the watchdog: 14 passed, rc 0, none skipped.
- ruff is clean.

Not run: the whole unit suite, the other browser files and `demo_check` (no example touched).
