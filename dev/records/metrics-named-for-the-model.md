# metrics-named-for-the-model: a model's items and parts are top-level metrics under their own names

The owner, 2026-11-23: "If we have items, I think we can treat them as top-level metrics, no? Users should feel like their items and their sensors are real parts of the system. They are not trying to explore ergostat internals, they are trying to explore their own data that they configured." Today a person sees 7 ergostat-named metrics (`ergostat_sensor`, `ergostat_block_output`, `ergostat_items`, ...) with the model's own names hidden in labels such as `part` and `kind`.

Change. In PromQL, each thing the model declares is a metric named for itself:
- each item kind: `<kind>_items{state, milestone...}` (a stock), `<kind>_transitions_total{from, to}` (a flow), `<kind>_time_in_state_seconds` (a histogram, the delay), `<kind>_last_transition_timestamp_seconds{from, to}`. So `gap_items{state="ready"}`, and the time since the last merge is `time() - max(gap_last_transition_timestamp_seconds{to="merged"})`.
- each stock, flow, auxiliary and sensor: a metric named for the part (`gaps_approved`, `merges_per_hour`), with the sensor's name as a label only when a part has several.
- names follow the model's system namespaces (a part's system prepended only where needed to keep names apart, the way the pages show them).
- ergostat's own internals (run cost, CPU, tokens, block outputs) keep the `ergostat_` prefix, so they read as the engine's, apart from the user's data.
Names are sanitised to valid PromQL (dashes to underscores), and two parts that would collide are refused at `ergostat check` with a fix. Labels stay bounded (never an item id).

Migration: write the new names, move existing readings to them (`ergostat migrate`), convert saved and default dashboard queries, and drop the old names once nothing reads them.

Definition of done.
1. On the factory model, autocomplete lists `gap_items`, `gaps_approved` and `merges_per_hour` as metrics; the old generic names list only engine internals.
2. A test model with two item kinds and a sensor shows each as its own metric in a real VictoriaMetrics (skipped when absent).
3. A collision test, and a test that no item id becomes a label.
4. The default dashboard's queries use the new names and answer as before.
5. Do not measure or change the live instance in the session.

## Where it stopped

Round 1, built (about 210 net lines outside tests and docs, within the 600 budget).

- `ergostat/promnames.py` (new): the names. An item kind K's metrics are `K_items`, `K_transitions_total`,
  `K_last_transition_timestamp_seconds`, `K_time_in_state_seconds` (`_bucket`, `_sum`, `_count`) and `K_field_total`.
  A part's sensor readings (`sensor/P.S`) go under `P`, with `sensor="S"` only when P has several sensors (an
  auxiliary's `set` counts as one when a block sets it). Names are sanitised to PromQL (dashes to underscores, never a
  leading digit). A part whose name a kind's metric takes, or that would start `ergostat_`, gets its system
  prepended. One that still collides, or a user kind that would read `ergostat_`, is a `metric-clash` error, which
  `spec.read` adds, so `ergostat check` refuses the model with the fix ("rename it, or put it in a system").
- `victoria.py`: readings are written under the model's names (`Victoria.spec_of`, set by `Project` and by
  `ergostat migrate`); every selector takes any name with the series' `series` label, so a record under an old name
  is still read until it is moved; `put` writes the item metrics under the kind's name (`item_labels`). The index's
  tally, checkpoint and balance keep their generic internal names, so `itemmetrics.py` is unchanged in logic.
- `migrate.py`: moves every series held under a name it is no longer written under (`ergostat_reading`,
  `ergostat_sensor`, a renamed part), and the old generic item metrics to their kind's names. The old is deleted only
  once every reading is read back under the new; an item sample not read back counts as `missing` and the old is kept.
- The built-in `ergostat` source reads a query naming the old generic metrics with an exact `part=` or `kind=` as the
  new (`promnames.convert`), with an `old-name` warning (a new verdict reason).
- SPEC §4b and §4e and docs/DASHBOARDS.md now describe the new names.

Decisions taken alone (each the more reversible choice):
- Saved queries are converted when they are read, not rewritten in the owner's YAML. Nothing is edited, and the old
  text still answers once its readings are moved.
- Valves (`ergostat_valve_position{valve}`), block outputs, a run's measures, observers, the index's
  `ergostat_events_total` and `ergostat_item_index_rebuilds_total`, and the built-in kinds' metrics
  (`ergostat_model_change_items`) stay the engine's. `ergostat_stage_seconds` (stages.py) is left as it was: it is a
  text exposition and is never written to the store.
- A system is prepended only for a clash with a kind's metric or the engine's prefix. Part names are unique within
  their kind, and a stock and a flow of one name write one series, so no two parts need separating otherwise.

Found, outside this gap (lesson 13): a stock and a flow with the same name share one sensor series (`Sensor.series` is
`sensor/NAME.SENSOR` whatever the part's kind). The factory's stock `gaps-approved` and flow `gaps-approved`
(dev/model/landing.yaml) both write `sensor/gaps-approved.main`, so their readings interleave. Both read as one metric,
`gaps_approved`. Fixing that belongs in a gap of its own.

Done items and their tests (tests/test_metrics_named_for_the_model.py):
1. `test_the_factory_names_its_items_and_parts_for_themselves`, `test_autocomplete_on_the_factory_lists_its_own_metrics`
   (`datasources.suggest` over a Prometheus-compatible stand-in that keeps what ergostat imports), and
   `test_autocomplete_on_the_factory_in_a_real_victoriametrics`. The old generic names are checked against an
   allowlist of engine internals.
2. `test_two_kinds_and_a_sensor_are_each_their_own_metric` (stand-in) and
   `test_two_kinds_and_a_sensor_in_a_real_victoriametrics`.
3. `test_a_part_whose_name_another_takes_is_refused_at_check_with_the_fix`,
   `test_a_kind_that_would_read_as_the_engines_is_refused`, `test_no_item_id_becomes_a_label`, and
   `test_no_example_has_a_metric_clash` (every example under examples/).
4. `test_the_default_dashboards_ask_no_old_name`: neither default dashboard asks PromQL. The model's
   (`dashboard_api.default`) charts refs and goals, and the page's overview (dashboard.js) asks moves, counts, items
   and SQL. So the test pins that no default, factory model file or documented query names an old generic metric.
   `test_a_query_saved_under_an_old_name_asks_the_new` covers conversion. `test_old_queries_answer_as_before_once_migrated`
   (real server) shows the old record answers alike before and after `ergostat migrate`, and holds nothing under the
   old names after it. `test_migrate_moves_the_item_metrics_and_keeps_any_not_read_back` covers the item move.
5. No live instance was measured or changed.

Seen to fail (lesson 9): with the clash problems dropped from `spec.read`, with `item_labels` made the identity, with
the conversion's text discarded, and with the missing-sample guard in `migrate._items` disabled. Each made the tests
above fail, and each was restored.

Not run here: no VictoriaMetrics binary is in this container, so every real-server test is skipped. That is the three
above, the real-server tests of test_metrics_store_labels.py, test_item_metrics.py and test_store_conformance.py, and
"in a real VictoriaMetrics" in done items 2 and 4, which has not been seen to pass. Also not run: the whole unit suite
and the four browser files (no page changed), and `demo_check` (no example touched). Run here, each passing:
test_metrics_named_for_the_model.py, test_metrics_store_labels.py (its migration stand-in and name tests updated to
the new names), test_item_metrics.py (two tests updated), test_item_metrics_balance.py, test_store_conformance.py,
test_data_sources.py and test_result_frames_and_verdicts.py. ruff is clean. Main was merged in (already up to date).

Known limits: when a part's sensor label is added or dropped under the same name, migrate does not move the old label
set; both are read by the `series` label. The conversion turns only exact `part="..."` and `kind="..."` matchers. A
query like `sum by (kind) (ergostat_items)` stays as written, and reads nothing once the record is moved.

## Entry

section: Runtime, scale and latency

- **A model's items and parts are top-level PromQL metrics under their own names** (built, on
  `metrics-named-for-the-model`; SPEC §4b, *Names and labels in PromQL*; docs/DASHBOARDS.md). Each item kind writes
  `KIND_items`, `KIND_transitions_total`, `KIND_last_transition_timestamp_seconds`, `KIND_time_in_state_seconds` and
  `KIND_field_total` (`gap_items{state="ready"}`). Each part's sensor is a metric named for the part (`gaps_approved`,
  `merges_per_hour`), with the sensor as a label only where a part has several. Only the engine's internals keep
  `ergostat_`. A clash is refused by `ergostat check` (`metric-clash`), with the fix. `ergostat migrate` moves
  readings held under old names, and a saved query naming the old generic metrics is read as the new. Left: the
  real-VictoriaMetrics tests have not run here (no binary), and a stock and a flow of one name still share one sensor
  series (a gap of its own).
