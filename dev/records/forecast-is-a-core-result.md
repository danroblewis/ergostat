# forecast-is-a-core-result: The forecast is one stable core result that the Timeline and anything else can read

depends-on: [forecast-promise-proposal]

Separate the forecast from the Timeline. `eta.py`'s result becomes a stable, versioned read model per item, group and stage, computed off the request path and reused until the record changes enough to matter.

Definition of done.
1. The Timeline reads this result and shows the same answers as before, proven by a test.
2. A dashboard panel can query it through a data source: forecast rows through a read-only view, aggregates by bounded labels.
3. A model read as a remote system exposes it, proven by a test with two instances.
4. Each answer states its basis, sample size and when it was computed, and says so when there is no estimate.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.
