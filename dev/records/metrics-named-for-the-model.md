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
