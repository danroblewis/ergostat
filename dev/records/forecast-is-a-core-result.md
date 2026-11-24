# forecast-is-a-core-result: The forecast is one stable core result that the Timeline and anything else can read

depends-on: [forecast-promise-proposal]

Separate the forecast from the Timeline. `eta.py`'s result becomes a stable, versioned read model per item, group and stage, computed off the request path and reused until the record changes enough to matter.

Definition of done.
1. The Timeline reads this result and shows the same answers as before, proven by a test.
2. A dashboard panel can query it through a data source: forecast rows through a read-only view, aggregates by bounded labels.
3. A model read as a remote system exposes it, proven by a test with two instances.
4. Each answer states its basis, sample size and when it was computed, and says so when there is no estimate.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.

## Where it stopped

Round 1, built. All four items are in the code, each with an acceptance test in `tests/test_forecast_result.py`.
Size: 296 net lines outside tests, docs and dev (150 net in eight files, plus the new `numbers/forecast.py` at 146),
within the 600 budget.

- **The result.** `ergostat/numbers/forecast.py` builds `forecast/v1` from `eta.simulate`. There is no second
  estimator. `simulate` gains `sets=`: for each named set of items, the same "last finish" it already gives a kind,
  read from the same runs. `etamodel.read` gains `Inputs.groups`: a parent named through a `group: true` relation
  (not a remote's), with its open members and itself. The eta worker (`web/eta_api._work`) now stores the forecast,
  so the Timeline's `merge`, the Items list and an item's page read it. Item keys are unchanged.
- **Done 1.** `test_the_timeline_reads_the_forecast_and_shows_the_same_answers` puts each item's eta, its bars and the
  kinds, capacity and other top-level keys side by side with the old composition (raw `simulate` plus `reasons`,
  kept in the test as it was in `_work`). It does this with no what-if and with `block.dev.pool:6`.
- **Done 2.** These are the `sql` source's views: `forecast_items` (one row per open item) and the aggregates
  `forecast_kinds`, `forecast_stages` and `forecast_groups`. Their labels are bounded by the model's kinds and states,
  and groups are capped at 200. The test is `test_a_panel_queries_forecast_rows_and_aggregates_through_the_sql_views`,
  which goes through the panel query API (`/api/query`). A query naming a forecast view while there is no forecast
  (being worked out, failed, no run) is refused with the reason. It never gets empty rows.
- **Done 3.** `/remote/v1/forecast` serves the forecast. The reader asks for it through
  `/api/forecast?remote=NAME` (`remote/items.forecast`, under the remote's per-period budget and lock). The test,
  `test_a_model_read_as_a_remote_exposes_its_forecast_to_the_model_reading_it`, uses two instances. Each is a web
  server with its own project, both in one process, with a token and a `remotes:` entry. Separate processes were not
  used.
- **Done 4.** Every item, kind, group and stage carries `runs`, `computed` and `basis`. For an item, `basis` is the
  block running or taking it and its recorded runs, or the state and its recorded stays and whose curve. The top
  level carries the window, seed, horizon, flags and what-if. `none` says why there is no estimate, and `p90_none`
  says why there is no p90. The tests are `test_each_answer_states_its_basis_sample_and_when_computed` and
  `test_no_estimate_is_said_never_read_as_none`.
- **Reused until it matters.** An answer is reused, unrun and with its version kept, when the simulation's inputs
  fingerprint the same (`forecast.fingerprint`) and it was computed within `KEPT` (120 s). The fingerprint covers
  item states, leases, attempts and relations, block pools, runs and switches, curve sizes, and arrival rates rounded
  to 0.1 an hour. The test is `test_the_forecast_is_reused_until_what_it_reads_changes`. `version` is one counter for
  every forecast the worker makes, so two different answers never share a version within a server's life (lesson 2).

Decisions taken alone (each the more reversible):

- `version` is not kept across restarts. Readers compare `version` together with `computed`. Persisting it later
  adds a file and breaks no reader.
- A **stage** is a kind's state that has open items now. It is said as when the items now in it have all finished,
  not when they have left it (the proposal's `stages.clears`). `clears` needs a per-run time of leaving the state,
  which `_Run` does not keep, so it is left out rather than claimed. It can be added later as a new key under the
  same schema.
- The proposal's other §1 keys are left to their own gaps. This definition does not ask for them: the quantile
  ladder (p05…p95, `beyond`), `waits_on` with `binding`, per-stage `enter` times and an `ergostat forecast` CLI.
  `/remote/v1/forecast` exposes the forecast only. The reading side's `forecast: true` relation (drawing a local
  item's wait from a remote ladder) belongs to remote-forecasts.
- `GET /api/forecast` and the remote's answer leave out the levelled schedule, which only the Timeline uses. At most
  500 items go in one answer, and the rest are counted in `items_left`.

Checked against the lessons: no lock is held across the reuse decision, but it only reads the worker's own cache
entry, taken under `_LOCK` when the job is popped, and the worker is the only writer (lesson 1). Versions come from a
sequence counter, not timestamps (lesson 2). A missing forecast, a failed one and a remote answer of another schema
each fail closed (lesson 3). Groups, item ids per ask (200) and items per answer (500) are capped (lesson 4).

Tests can fail (lesson 9). Two breaks were made and watched fail, then undone. Dropping `eta.reasons`' words from the
built forecast failed done 1 with `KeyError: 'waits_in'`. Removing the SQL source's "being worked out" refusal failed
done 2.

Tests run here, one file at a time:
- `tests/test_forecast_result.py`: 7 passed.
- `tests/test_sql_source.py`: passed. Two edits there: the editor's view list now includes the forecast views, and
  the index-layout test skips them because they are not built from the index.
- `tests/test_eta.py`, `test_remote_items.py`, `test_remote.py`, `test_graph_cli_web.py`,
  `test_dashboard_first_load.py`, `test_take_order.py`, `test_precedence.py`, `test_relations.py`: all passed.
  One page test in `test_dashboard_first_load.py` skipped because playwright was not installed for that run.
- `ruff`: clean.

The browser file `tests/test_items_page.py`, under the watchdog, had 86 passed and 4 failed:
- `test_a_lease_taken_or_ended_comes_and_goes_in_the_valves_panel` and
  `test_the_graph_and_the_timeline_left_open_change_nothing[graph]` both pass when run again alone (3 passed). They
  are load timing in the full file, and their cause was not found here.
- `test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart` (the project switcher's option never
  appears) and `test_every_surface_prints_the_servers_one_count_of_goals_off` (the Loops page heading reads "Goals ·"
  where the test expects "Loops ·") fail alone too. They test the project switcher and the Loops page heading, and
  this branch changes no JS, no status and no project listing. They were not run on clean main here.

Not run here: the whole unit suite, the other three browser files and `demo_check` (no example was touched). The
live instance was not measured or touched.

## Entry

section: Modelling

- **The forecast is one stable core result** (done, on `forecast-is-a-core-result`; SPEC §5a *The forecast*, §4c,
  §4e): the eta worker keeps `forecast/v1` (`numbers/forecast.py`), made from the one Monte Carlo, per item, kind,
  group (a `group: true` parent) and stage (a kind's state). Every answer gives its basis, runs and the time it was
  computed, and says `none` (why) when there is no estimate. It is versioned, and it is reused unrun while what the
  simulation reads is unchanged. The Timeline, the Items list and an item's page read it with the same answers as
  before. Other readers: `GET /api/forecast`, the `sql` source's `forecast_items`, `forecast_kinds`,
  `forecast_stages` and `forecast_groups` views, and `/remote/v1/forecast`, which a reading model asks through
  `/api/forecast?remote=NAME`. Not done: the quantile ladder, `waits_on` with binding, a stage's time to clear, the
  CLI, and the reading side's `forecast: true` relation (remote-forecasts).
