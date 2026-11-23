# chart-result-shapes: Each query result has a shape, and the shape decides which charts apply

depends-on: [data-source-model, panel-editor-sidebar-simplified]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. Every result is one of a small set of typed frames: time series; dimensions to measures; points; distribution; two signals (input and output); and a transfer function from a model. Each chart family declares the shapes it takes. Charts that cannot show the current shape are disabled, and the chart dialog shows those that can, rendered on the data. A shape mismatch says how to reshape the data in one sentence. Add a few client-side transforms only where a query language cannot do it: pivot, join by field, group.

Definition of done.
1. A table of every chart family against every shape is tested.
2. Switching among applicable charts never re-asks the data source.
3. A PromQL and a SQL result of the same shape draw the same chart.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Use the five shapes and the result envelope in section 2 of the catalog. "Two signals" is a `series` with `input` and `output` roles. Client-side transforms are for reshaping only.
