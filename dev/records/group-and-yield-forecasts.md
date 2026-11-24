# group-and-yield-forecasts: Forecasts for groups: how many of a set finish by a date, allowing for loss

depends-on: [forecast-is-a-core-result]

From the same simulation, answer group questions: how many of a declared set finish by a date, the chance at least N do, expected loss, and how many to start to get N out at a stated confidence.

Definition of done.
1. Tests on a fixture with a known yield recover the right counts within stated bounds.
2. A second fixture, a job shop with rework, gets correct group answers with no special case.
3. The answers are available to dashboard panels.

Boundary (the owner, 2026-11-23). ergostat serves job shops with rework, batch and yield production, and make-to-stock alike. No production style is a principle of the core. The core offers general parts, off unless a model declares them, and names no gaps, merges, software or factories. The ergostat-on-ergostat factory is one user, a job shop with rework, and its choices live in its own model. A model read as a remote system must be able to expose these answers to the model reading it.

Build on what exists: the Monte Carlo over every open item (`ergostat/numbers/eta.py`, `etamodel.py`), its what-if overrides, its backtest (`tests/eta_backtest.py`), and the Timeline's calibration line. Do not start a second estimator.

Do not measure or change the live instance in the session.
