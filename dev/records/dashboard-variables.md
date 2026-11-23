# dashboard-variables: Dashboard variables, including repeated panels by a variable

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change. A dashboard has variables, like `$kind`, from a query (`label_values(metric, label)`), a constant or a custom list, single or multi-value, shown at the top and kept in the address. Queries interpolate them safely for each language. Repeated panels (`dashboard-layout-like-grafana`) repeat by a variable.

Definition of done.
1. Changing a variable re-runs only panels that use it.
2. A value containing quotes or regex characters cannot change a query's meaning.
3. A panel repeated by a variable follows its selected values.

## Amendment from the chart catalog

See `docs/research/2026-11-23-charts/catalog.md` section 7.2. Safe interpolation also covers the `analysis` and `model` query languages when they exist.
