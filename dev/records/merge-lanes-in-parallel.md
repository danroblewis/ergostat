# merge-lanes-in-parallel: Batches are tested in parallel lanes, split by the paths they touch

The queue runs one batch at a time while approved work waits. Allow several lanes: batches whose changed paths do not overlap are tested at once, and a speculative lane may test the next batch on top of the current one, discarded if the current one fails. Lanes are bounded by measured CPU and memory, since the machine is CPU-limited.
Done: 1. Tests: non-overlapping batches land in parallel; overlapping ones are serialised; a failed base discards its speculative lane. 2. A fixture replay shows merges per hour against one lane. 3. Lanes never exceed the declared resource bounds.

The owner's decisions behind this (2026-11-23): more delivered work per AI dollar; tests exist for regressions; prefer program and rule checks over AI review; any path that checks less before merge needs a way to find and revert regressions on main. General parts go in ergostat's core as options a model declares (off unless declared, naming no gaps or software); this factory is the first user. Do not measure or change the live instance in the session: the coordinator applies changes.
