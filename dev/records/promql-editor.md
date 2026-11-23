# promql-editor: A PromQL editor with highlighting and autocomplete for metrics, labels and values

depends-on: [data-source-model]

Owner's design, 2026-11-23. A dashboard data source is, as in Grafana, a connection, a query language and a typed result. Each panel query is text in its source's language. Visual query builders are not wanted. Metrics hold aggregates over bounded labels; anything with a generated ID stays in the event log. The event log remains the source of truth.

Change.
- The query box for a Prometheus-compatible source is a code editor with PromQL syntax highlighting and autocomplete for functions, metric names, label names and label values, from the source's metadata APIs through our server.
- The owner's exploration pattern works and is shown as a starting hint: `count by(__name__)({__name__=~".+"})`.
- Run with a shortcut; errors appear at the position the server reports.
- Library code is vendored at a pinned version, with no build step added to the page.

Definition of done.
1. A browser test completes a metric name, a label and a label value against a stub source.
2. A syntax error is marked where it is.
3. Autocomplete stays bounded on a source with 100,000 series.
