# error-budget-sets-check-level: An error budget sets how much checking a change gets

depends-on: [merge-first-verify-after-proposal]

A general control loop: a budget of regressions reaching main per window; while it is healthy, the declared check level for low-risk changes drops (fewer pre-merge tests, no blocking review); as it burns, checks tighten. It requires the retroactive fix path from merge-first-verify-after-proposal and stays off until that exists.
Done: 1. Tests: the level moves with the budget, both ways, with a recorded reason. 2. With no retroactive mechanism declared, the level never drops. 3. The budget and level are dashboard series.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
