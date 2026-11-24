# item-metrics-from-the-log: Item counts, transitions and durations become log-derived metrics

depends-on: [metrics-store-with-labels]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. A job maintains these from the item index, never replaying the log per request, and never copying individual events:
- `ergostat_items{kind,state}` gauge (a stock);
- `ergostat_item_transitions_total{kind,from,to}` counter (a flow);
- `ergostat_item_time_in_state_seconds_bucket{kind,state,le}` histogram (a delay);
- `ergostat_item_field_total{kind,field}` counter;
- `ergostat_events_total{type,source}` counter.
- `ergostat_item_last_transition_timestamp_seconds{kind,from,to}` gauge, so a person can ask how long since something last happened, for example the owner's "how long since the last successful merge": `time() - max(ergostat_item_last_transition_timestamp_seconds{kind="gap",to="merged"})`. A test answers exactly that query.
Labels are bounded. An item id, branch, session or commit is never a label, enforced by a guard with a cardinality limit. Milestone may be a label where the kind has one. History is backfilled from the index, and a restart neither loses nor double counts.

Definition of done.
1. On a hand-worked record, each metric equals the count from the index at every minute.
2. Ten items in and ten out between two samples shows in the counter though the gauge is unchanged.
3. Backfill then live updates produce no gap or double count.
4. A field with unbounded values is refused as a label.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Name the system's two edges with reserved states: an arrival (a move with no `from` in the index) is `from="(new)"`, and an item the index forgets is `to="(gone)"`, so the gauge's change equals net transitions. Backfill states what pruned history it cannot recover. `time_in_state` is observed at exit, so it cannot see stuck work: say so in its help text.
