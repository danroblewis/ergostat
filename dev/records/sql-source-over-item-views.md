# sql-source-over-item-views: A read-only SQL data source over stable item views

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. For what PromQL cannot do (which items, per-item comparisons, exact medians, cohorts), a SQL source over documented, stable, read-only views such as `gaps`-style per-kind views, `transitions` and `item_fields`. The internal tables are never exposed. SQLite's authorizer allows only SELECT on those views, with time, row and memory limits. Provide `median` and percentile aggregates. The editor has SQL highlighting and autocomplete for views and columns.

Definition of done.
1. Writes, ATTACH, PRAGMA and any internal table are refused (tests).
2. A runaway query is stopped at its limit.
3. Views survive an index layout change.
4. Exact medians match a hand-worked record.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Add an `item_spans` view with open items, re-entry number and terminal reason, for survival, aging and exact Little's law.
