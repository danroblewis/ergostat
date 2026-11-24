# forecast-promise-proposal: Proposal: forecasts, quotes, frozen windows and calibration as general core parts

depends-on: [control-aware-estimates-proposal]

Write `docs/proposals/forecasts-and-promises.md`, settling the design the later gaps in this milestone build.

The owner wants to add work knowing it will be done in the right order, with its prerequisites, and what it does to the timeline. Estimates must be abstracted from the Gantt so other features can use them.

Settle:
1. The forecast as a stable result: per item, per group and per stage; finish-time ranges, what it waits on, its basis and its sample size.
2. Promise types a model may use: per-item date, a quantity by a date (N of M), a service level, and starting extra to cover expected loss.
3. How each of the three models contributes: the process model (paths, stage times, rework), system dynamics (aggregate capacity and flow), control (gates, release, pools). Agree with control-aware-estimates-proposal and do not repeat it.
4. A quote: hypothetical items run through the forecast without touching the record, and what it reports.
5. A frozen window: what it protects, how it is declared, how urgent work overrides it, and its effect in the simulation.
6. Calibration: what is recorded when a forecast is made, how it is scored, and how results feed back.
7. How a remote system's forecasts are read by another model.
8. The build split, confirming or amending the gaps of this milestone.

Definition of done.
1. The proposal settles all eight, with a worked example for a job shop with rework and one for a batch process with yield loss.
2. It names what already exists and what is new.
3. Any question for the owner is one sentence.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.
