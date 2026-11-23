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

## Where it stopped

Round 1 stopped before any building, 2026-11-23. The session's tool permissions refused every shell command: both
`git -C /work status --short` and a first read-only look (`cat ... && which victoria-metrics ...`) were denied
("don't ask mode"). With no shell, the session could not run pytest, ruff or a VictoriaMetrics binary, and could not
`git add` or `git commit`. That means none of done items 1-3 could be tested, and the branch could not record any
work. This section is written to the working tree but is **not committed**, because committing needs the shell too.

Done: nothing outside this section. ergostat/victoria.py, CLAUDE.md and this definition were read.

Left: all of it. That covers the migration with its idempotence test against a real binary (skipped when absent),
bounded series labels, the built-in Prometheus-compatible data source, the SQLite message on PromQL panels, the
supervised VictoriaMetrics process, the guide text, and the `rate()`/`increase()` comparison against Prometheus.

Why: this is the environment, not the gap. No dependency is missing. I chose the most reversible option and wrote
no untested code into the tree. Rerun the round with Bash allowed (at least `git`, `uv run`, and the test and ruff
scripts).

## Where it stopped

Parked by the factory (review/metrics-store-with-labels-1, 2026-11-23 09:15).

Done: only the definition of done and a Where it stopped note, committed. Left: everything in the definition (migration plus idempotence test against a real VictoriaMetrics binary, bounded labels, the built-in Prometheus data source, the SQLite PromQL-panel message, the supervised process and default-for-new-installs, the guide text, the rate()/increase() comparison). Why stop: the build session's tool permissions refused every shell command, so it could not run git, uv, pytest, ruff or the binary. A fix round in the same environment would fail the same way. This is an environment cause, not a fault in the gap's approach.

## Where it stopped

Round 2 stopped before any building, 2026-11-23. The queue's note said the shell fault was gone, but it was not:
the session's tool permissions again refused every shell command ("don't ask mode"). Two commands were refused, as
given: `git status --short && git log --oneline -3 && wc -l CLAUDE.md NOTES.md ergostat/victoria.py && cat
ergostat/victoria.py && which victoria-metrics victoria-metrics-prod ...`, and then the plain
`git -C /work status --short`. Without a shell this session cannot run pytest, ruff, `scripts/named_tests.py` or a
VictoriaMetrics binary, and cannot `git add` or `git commit` (a third command, `git -C /work add
dev/records/metrics-store-with-labels.md && git -C /work commit -m "..."`, was refused too). This section is written to the working tree only and is
**not committed**.

Done: nothing outside this section.

Left: everything in the definition, as listed in the round-1 note above.

Why: the environment, for the second time in a row. No dependency is missing. I took the most reversible option and
wrote no untested code: code that cannot be run or committed would fail review (done means tests pass and the work is
committed). Do not schedule round 3 until a session's Bash is shown to work, for example by running
`git -C /work status --short` as the session's first command before the gap is handed over.
