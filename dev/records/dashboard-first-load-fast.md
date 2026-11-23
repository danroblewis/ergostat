# dashboard-first-load-fast: a cold dashboard draws in a few seconds

depends-on: [dashboard-v2]

Measured 2026-11-23: on a cold server under load, the first load takes about 24 s, in two requests of about 10 s each. Which query is slow is not known.

Change. Measure each query of the default dashboard on a factory-size record (`factory_state`), find what dominates, and serve it from the item index or a cached roll-up. Panels above the fold are asked for first.

Definition of done.
1. A test on the factory-size record holds the default dashboard's first answer under a stated budget on a cold server.
2. Each query's time is recorded in the test's output.
3. Answers are identical to before.

Files: ergostat/query/, ergostat/spec/itemindex.py, tests.

## Where it stopped

Round 1 (2026-11-23). Nothing built: this gap waits for `dashboard-v2`, which is not on main.

- What is missing on main (the clone's `main`, e43046dc): there is no Dashboard page and no dashboard query to
  measure. `ergostat/query/` (named in Files) does not exist. No `/dashboard` route or `/api/dashboard` handler is in
  `ergostat/web/` (a search for "dashboard" there finds nothing). No `dev/records/dashboard-v2.md` or
  `dashboard-page-v1.md` exists, and no commit names either. The only dashboard work on main is the proposal
  (docs/proposals/dashboard.md, prose; its section 8 gives the default's panels) and the chart forms
  (static/plots.js, not used by any page).
- So none of the three done items can be met: there is no "default dashboard's first answer" to hold under a
  budget, no per-query times to record, and no "before" answer to compare with.
- Decision taken alone (most reversible): not to put another page (say `/` with its /api/status and /api/graph) in
  the dashboard's place. That would mean guessing what the 24 s measurement was of, and building outside the gap.
  When `dashboard-v2` lands on main, this gap starts again from its definition as written, with no code from this
  round to undo.
- Left: everything in the definition. That means measuring each query of the default dashboard on `factory_state`,
  serving the dominant one from the item index or a cached roll-up, asking for above-the-fold panels first, and the
  three tests.

Not run: no test and no ruff, because no code changed (this section is the only change). main has not moved since
the branch was made, so there was nothing to merge.

## Where it stopped

Parked by the factory (review/dashboard-first-load-fast-1, 2026-11-23 03:34).

Done: only the definition of done and a 'Where it stopped' note; no code, no tests. Left: everything. Measure each query of the default dashboard on factory_state, serve the dominant one from the item index or a cached roll-up, ask for above-the-fold panels first, and write the three acceptance tests (cold first answer under a stated budget, per-query times in the output, answers identical to before). Why stop: there is no dashboard on main to measure. ergostat/query/ and the dashboard route and handler arrive with gap/dashboard-v2 (origin/factory/dashboard-v2, 762ad7eb), which is not an ancestor of origin/main.
