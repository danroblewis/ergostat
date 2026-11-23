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
