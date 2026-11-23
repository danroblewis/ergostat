# dashboard-first-load-fast: a cold dashboard draws in a few seconds

depends-on: [dashboard-v2]

Measured 2026-11-23: on a cold server under load, the first load takes about 24 s, in two requests of about 10 s each. Which query is slow is not known.

Change. Measure each query of the default dashboard on a factory-size record (`factory_state`), find what dominates, and serve it from the item index or a cached roll-up. Panels above the fold are asked for first.

Definition of done.
1. A test on the factory-size record holds the default dashboard's first answer under a stated budget on a cold server.
2. Each query's time is recorded in the test's output.
3. Answers are identical to before.

Files: ergostat/query/, ergostat/spec/itemindex.py, tests.
