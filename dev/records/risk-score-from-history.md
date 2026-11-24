# risk-score-from-history: Each change gets a risk score learned from what failed before

Score a change from its history: paths touched and their failure rates, size, author block, gap kind, conflicts. Validate on past batches (did high scores fail more?). The score is a general item measure a model can use to route checks (error-budget-sets-check-level, merge-lanes-in-parallel).
Done: 1. A backtest on the factory record shows calibration (failure rate by score band). 2. The score is on each item and queryable.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
