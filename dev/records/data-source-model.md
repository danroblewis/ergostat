# data-source-model: Dashboard panels query named data sources in each source's own language

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Problem. The panel editor's Sources (Metrics, Events, Items per state, Item moves, ...) are hand-made forms over internal stores, not data sources.

Change.
- A data source has a name, a type, its connection, a query language and a read-only `query` that returns a typed result. Types are pluggable, so SQL, Redis, Kafka or a cloud monitoring source can be added later without changing panels.
- Reuse the model's existing `sources:` (type prometheus) rather than a second configuration.
- A panel query is `{source, text}` plus display options. Results use the shapes of `chart-result-shapes`.
- Every query is bounded in time, points and series, read-only, and refused clearly when it exceeds them.
- The first type is Prometheus-compatible, through the server (the browser never holds a source's credentials).
- Old panels keep working until `retire-old-query-forms`.

Definition of done.
1. A panel runs a PromQL range query against a stub Prometheus and draws it.
2. Adding a data source type needs one module and no change to panels (a test adds a fake type).
3. A query over the limits, an unreachable source and a bad query each give a clear error in the panel.
4. No write path to any source exists.
